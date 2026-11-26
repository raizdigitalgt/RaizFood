from fastapi import HTTPException
from sqlalchemy import select

from app import pos_models as p
from app import restaurant_models as m
from app.models import now
from app.pos_service import (
    check_version,
    notify,
    open_lines,
    refresh_status,
    rows,
    save,
    trace,
)
from app.restaurant_records import get_row


def authorized_areas(db, access, actor):
    if "kitchen.all_areas" in access.permissions:
        return None
    table = p.kitchen_access
    return set(
        db.scalars(
            select(table.c.preparation_id).where(
                table.c.tenant_id == access.tenant.id, table.c.user_id == actor.id
            )
        )
    )


def check_area(db, access, actor, ticket):
    allowed = authorized_areas(db, access, actor)
    if allowed is not None and ticket["preparation_id"] not in allowed:
        raise HTTPException(404, "Comanda no disponible")


def kitchen_view(db, actor, access, area=None):
    tenant = access.tenant.id
    allowed = authorized_areas(db, access, actor)
    conditions = [p.tickets.c.state.in_(("new", "preparing", "ready"))]
    if allowed is not None:
        conditions.append(p.tickets.c.preparation_id.in_(allowed))
    if area == "general":
        conditions.append(p.tickets.c.preparation_id.is_(None))
    elif area:
        conditions.append(p.tickets.c.preparation_id == area)
    recent = now() - 86400
    conditions.append((p.tickets.c.state != "ready") | (p.tickets.c.ready_at >= recent))
    tickets = rows(db, p.tickets, tenant, *conditions, order_by=(p.tickets.c.number,))
    ticket_ids = [ticket["id"] for ticket in tickets]
    order_ids = {ticket["order_id"] for ticket in tickets}
    order_lookup = {
        row["id"]: row for row in rows(db, p.orders, tenant, p.orders.c.id.in_(order_ids))
    }
    tables = {
        row["id"]: row["name"] or f"Mesa {row['number']}"
        for row in rows(
            db,
            m.tables,
            tenant,
            m.tables.c.id.in_(
                {order["table_id"] for order in order_lookup.values() if order["table_id"]}
            ),
        )
    }
    entries = rows(db, p.ticket_lines, tenant, p.ticket_lines.c.ticket_id.in_(ticket_ids))
    grouped = {key: [] for key in ticket_ids}
    for line in entries:
        grouped[line["ticket_id"]].append(line)
    for ticket in tickets:
        order = order_lookup[ticket["order_id"]]
        ticket.update(
            items=grouped[ticket["id"]],
            order_version=order["version"],
            current_table_id=order["table_id"],
            current_table=tables.get(order["table_id"]),
        )
    areas = [
        area
        for area in rows(db, m.preparation, tenant, order_by=(m.preparation.c.position,))
        if allowed is None or area["id"] in allowed
    ]
    return {"tickets": tickets, "areas": areas, "general": allowed is None}


def update_kitchen(db, actor, access, key, data):
    tenant = access.tenant.id
    ticket = get_row(db, p.tickets, tenant, key)
    check_area(db, access, actor, ticket)
    order = get_row(db, p.orders, tenant, ticket["order_id"])
    check_version(order, data.version)
    if ticket["state"] == "cancelled":
        raise HTTPException(409, "La comanda fue sustituida o cancelada")
    entries = rows(db, p.ticket_lines, tenant, p.ticket_lines.c.ticket_id == key)
    changed = [
        entry
        for entry in entries
        if entry["state"] not in {"cancelled", "ready"}
        and (data.ticket_line_id is None or entry["id"] == data.ticket_line_id)
    ]
    if (
        not changed
        or (data.state == "preparing" and ticket["state"] != "new")
        or (data.state == "ready" and ticket["state"] != "preparing")
    ):
        raise HTTPException(409, "La comanda ya cambió de estado")
    for entry in changed:
        save(db, p.ticket_lines, tenant, {"state": data.state}, entry["id"])
        entry["state"] = data.state
        if ticket["kind"] in {"cancellation", "transfer"}:
            continue
        line = get_row(db, p.lines, tenant, entry["line_id"])
        if line["revision"] == entry["revision"] and line["status"] in {"sent", "preparing"}:
            save(db, p.lines, tenant, {"status": data.state}, line["id"])
    state = (
        "ready" if all(row["state"] in {"ready", "cancelled"} for row in entries) else "preparing"
    )
    save(
        db,
        p.tickets,
        tenant,
        {
            "state": state,
            "started_at": ticket["started_at"] or now(),
            "ready_at": now() if state == "ready" else None,
        },
        key,
    )
    status = (
        order["status"]
        if order["status"] == "cancelled"
        else refresh_status(order, open_lines(db, tenant, order["id"]))
    )
    version = order["version"] + 1
    save(db, p.orders, tenant, {"status": status, "version": version}, order["id"])
    trace(
        db,
        actor,
        tenant,
        order["id"],
        "kitchen_state",
        {
            "ticket": key,
            "before": ticket["state"],
            "after": state,
            "lines": [row["id"] for row in changed],
        },
    )
    notify(db, actor, tenant, "pos.kitchen.updated", key)
    return {"id": key, "state": state, "version": version}
