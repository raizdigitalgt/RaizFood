from collections import Counter, defaultdict
from hashlib import sha256
from json import dumps

from fastapi import HTTPException
from sqlalchemy import delete, insert, literal_column, select, update
from sqlalchemy.dialects.sqlite import insert as upsert

from app import pos_models as p
from app import restaurant_models as m
from app.access import audit
from app.models import Membership, RolePermission, User, now
from app.pos_schemas import PosConfig
from app.restaurant_catalog import calculate
from app.restaurant_records import condition, get_row, scoped_rows


def rows(db, table, tenant, *where, order_by=()):
    query = scoped_rows(db, table, tenant).where(*where)
    return [dict(row) for row in db.execute(query.order_by(*order_by)).mappings()]


def save(db, table, tenant, data, key=None):
    if key:
        db.execute(
            update(table).where(condition(table, tenant, key)).values(**data, updated_at=now())
        )
        return key
    return db.execute(insert(table).values(tenant_id=tenant, **data)).inserted_primary_key[0]


def next_number(db, tenant, kind):
    seq = p.sequences
    return db.scalar(
        upsert(seq)
        .values(tenant_id=tenant, kind=kind, value=1)
        .on_conflict_do_update(
            index_elements=["tenant_id", "kind"], set_={"value": seq.c.value + 1}
        )
        .returning(seq.c.value)
    )


def settings(db, tenant):
    return db.scalar(select(m.settings.c.preferences).where(m.settings.c.tenant_id == tenant)) or {}


def pos_config(db, tenant):
    return PosConfig.model_validate(settings(db, tenant).get("pos", {}))


def notify(db, actor, tenant, event, subject):
    audit(db, actor, event, subject, tenant)


def trace(db, actor, tenant, order_id, action, changes):
    save(
        db,
        p.history,
        tenant,
        {"order_id": order_id, "actor_id": actor.id, "action": action, "changes": changes},
    )
    notify(db, actor, tenant, f"pos.order.{action}", order_id)


def idempotent(db, tenant, actor, action, data, apply):
    raw = data.model_dump(mode="json", exclude={"request_id"})
    checksum = sha256(dumps([action, raw], sort_keys=True).encode()).hexdigest()
    table = p.idempotency
    existing = db.execute(
        select(table.c.fingerprint, table.c.result).where(
            table.c.tenant_id == tenant,
            table.c.actor_id == actor.id,
            table.c.request_id == data.request_id,
        )
    ).first()
    if existing:
        if existing.fingerprint != checksum:
            raise HTTPException(409, "La clave de reintento ya se usó con otros datos")
        return existing.result
    result = apply()
    db.execute(
        insert(table).values(
            tenant_id=tenant,
            actor_id=actor.id,
            request_id=data.request_id,
            fingerprint=checksum,
            result=result,
            created_at=now(),
        )
    )
    return result


def check_version(row, requested):
    if row["version"] != requested:
        raise HTTPException(409, "El pedido cambió. Actualiza el estado y vuelve a intentarlo")


def check_waiter(db, access, actor, key):
    if not key:
        return
    if key != actor.id:
        access.require("orders.assign")
    membership = db.get(Membership, (key, access.tenant.id))
    user = db.get(User, key)
    if (
        not membership
        or not membership.active
        or not user
        or not user.active
        or user.platform_admin
        or not db.get(RolePermission, (access.tenant.id, membership.role_id, "orders.create"))
    ):
        raise HTTPException(404, "Mesero no disponible")


def free_table(db, tenant, key):
    table = get_row(db, m.tables, tenant, key)
    area = get_row(db, m.areas, tenant, table["area_id"])
    if not area["active"] or table["state"] != "available":
        raise HTTPException(409, "La mesa no está disponible")
    if db.scalar(
        select(p.orders.c.id)
        .where(condition(p.orders, tenant), p.orders.c.table_id == key, p.active_table)
        .limit(1)
    ):
        raise HTTPException(409, "La mesa ya tiene un pedido activo")
    return table


def mark_table(db, actor, tenant, key, state):
    if key:
        save(db, m.tables, tenant, {"state": state}, key)
        notify(db, actor, tenant, "pos.table.updated", key)


def begin_order(db, actor, access, data):
    tenant = access.tenant.id
    if data.mode not in settings(db, tenant).get("order_modes", ["dine_in"]):
        raise HTTPException(422, "La modalidad no está habilitada")
    check_waiter(db, access, actor, data.waiter_id)
    if data.mode == "dine_in":
        if not data.table_id:
            raise HTTPException(422, "Selecciona una mesa")
        free_table(db, tenant, data.table_id)
    elif data.table_id or data.guests:
        raise HTTPException(422, "La modalidad no admite mesa ni comensales")
    contact = data.model_dump(include={"name", "phone", "address", "reference", "estimated_at"})
    if data.customer_id:
        client = get_row(db, m.customers, tenant, data.customer_id)
        if not client["active"]:
            raise HTTPException(422, "El cliente está inactivo")
        for key in ("name", "phone", "address"):
            contact[key] = contact[key] or client[key]
    if data.mode == "delivery" and not all(contact[k] for k in ("name", "phone", "address")):
        raise HTTPException(422, "Ingresa nombre, teléfono y dirección de entrega")
    if data.mode != "delivery" and data.shipping_cents:
        raise HTTPException(422, "El envío corresponde a pedidos a domicilio")
    number = next_number(db, tenant, "order")
    key = save(
        db,
        p.orders,
        tenant,
        dict(
            number=number,
            mode=data.mode,
            table_id=data.table_id,
            customer_id=data.customer_id,
            creator_id=actor.id,
            waiter_id=data.waiter_id or actor.id,
            guests=data.guests,
            status="draft",
            financial_status="unpaid",
            notes=data.notes,
            version=1,
            contact=contact,
            delivery_state="pending" if data.mode == "delivery" else "",
            shipping_cents=data.shipping_cents,
            subtotal_cents=0,
            discount_cents=0,
            total_cents=data.shipping_cents,
            seated_at=now() if data.table_id else None,
        ),
    )
    save(db, p.accounts, tenant, {"order_id": key, "name": "Principal", "position": 0})
    mark_table(db, actor, tenant, data.table_id, "occupied")
    trace(db, actor, tenant, key, "created", {"status": "draft", "mode": data.mode})
    return {"id": key, "number": number, "version": 1}


def order_lines(db, tenant, key):
    return rows(
        db,
        p.lines,
        tenant,
        p.lines.c.order_id == key,
        order_by=(literal_column("order_items.rowid"),),
    )


def open_lines(db, tenant, key):
    return [line for line in order_lines(db, tenant, key) if line["status"] != "cancelled"]


def get_line(db, tenant, order_id, key):
    row = get_row(db, p.lines, tenant, key)
    if row["order_id"] != order_id or row["status"] == "cancelled":
        raise HTTPException(404, "Producto del pedido no disponible")
    return row


def portion(amount, weights):
    total = sum(weights)
    if not total:
        return [amount, *([0] * (len(weights) - 1))] if weights else []
    ratios = [divmod(amount * weight, total) for weight in weights]
    values = [quotient for quotient, _ in ratios]
    order = sorted(range(len(weights)), key=lambda i: (-ratios[i][1], i))
    for index in order[: amount - sum(values)]:
        values[index] += 1
    return values


def applied_discount(amount, rule):
    if not rule:
        return 0
    if rule["kind"] == "fixed":
        return min(amount, rule["value"])
    return min(amount, (amount * rule["value"] + 5000) // 10000)


def totals(db, tenant, order, active):
    key = order["id"]
    rules = {
        row["line_id"]: row for row in rows(db, p.discounts, tenant, p.discounts.c.order_id == key)
    }
    bases = [line["unit_cents"] * line["quantity"] for line in active]
    line_discounts = [
        applied_discount(amount, rules.get(line["id"]))
        for line, amount in zip(active, bases, strict=True)
    ]
    nets = [base - discount for base, discount in zip(bases, line_discounts, strict=True)]
    apportioned = portion(applied_discount(sum(nets), rules.get(None)), nets)
    combined = [local + general for local, general in zip(line_discounts, apportioned, strict=True)]
    summary = {
        "subtotal_cents": sum(bases),
        "discount_cents": sum(combined),
        "total_cents": sum(bases) - sum(combined) + order["shipping_cents"],
    }
    return summary, dict(zip((line["id"] for line in active), combined, strict=True))


def account_rows(db, tenant, key):
    return rows(
        db, p.accounts, tenant, p.accounts.c.order_id == key, order_by=(p.accounts.c.position,)
    )


def account_breakdown(db, tenant, order, active, deductions):
    key = order["id"]
    accounts = account_rows(db, tenant, key)
    portions = rows(db, p.allocations, tenant, p.allocations.c.order_id == key)
    by_line = {(row["line_id"], row["account_id"]): row["quantity"] for row in portions}
    for account in accounts:
        account.update(lines=[], subtotal_cents=0, discount_cents=0)
    for line in active:
        weights = [by_line.get((line["id"], account["id"]), 0) for account in accounts]
        if len(accounts) == 1:
            weights = [line["quantity"]]
        shares = portion(deductions[line["id"]], weights)
        for account, quantity, discount in zip(accounts, weights, shares, strict=True):
            if quantity:
                gross = line["unit_cents"] * quantity
                account["lines"].append(
                    {"line_id": line["id"], "quantity": quantity, "discount_cents": discount}
                )
                account["subtotal_cents"] += gross
                account["discount_cents"] += discount
    shipping = portion(
        order["shipping_cents"], [a["subtotal_cents"] - a["discount_cents"] for a in accounts]
    )
    for account, fee in zip(accounts, shipping, strict=True):
        account["shipping_cents"] = fee
        account["total_cents"] = account["subtotal_cents"] - account["discount_cents"] + fee
    return accounts


def split_account(db, tenant, order, data):
    key = order["id"]
    accounts = account_rows(db, tenant, key)
    source = next(
        (row for row in accounts if row["id"] == (data.source_id or accounts[0]["id"])), None
    )
    if not source:
        raise HTTPException(404, "Cuenta no disponible")
    active = open_lines(db, tenant, key)
    initial = len(accounts) == 1
    available = (
        {line["id"]: line["quantity"] for line in active}
        if initial
        else {
            row["line_id"]: row["quantity"]
            for row in rows(db, p.allocations, tenant, p.allocations.c.account_id == source["id"])
        }
    )
    selected = {part.line_id: part.quantity for part in data.items}
    if len(selected) != len(data.items) or any(
        quantity > available.get(line, 0) for line, quantity in selected.items()
    ):
        raise HTTPException(422, "La cuenta no contiene esas cantidades")
    if sum(selected.values()) == sum(available.values()):
        raise HTTPException(422, "Conserva al menos un producto en la cuenta de origen")
    target = save(
        db,
        p.accounts,
        tenant,
        {"order_id": key, "name": data.name, "position": accounts[-1]["position"] + 1},
    )
    db.execute(
        delete(p.allocations).where(
            condition(p.allocations, tenant), p.allocations.c.account_id == source["id"]
        )
    )
    for line, quantity in available.items():
        take = selected.get(line, 0)
        for account_id, count in ((source["id"], quantity - take), (target, take)):
            if count:
                save(
                    db,
                    p.allocations,
                    tenant,
                    {"order_id": key, "account_id": account_id, "line_id": line, "quantity": count},
                )
    return {"source_id": source["id"], "account_id": target, "quantities": selected}


def combine_accounts(db, tenant, order):
    key = order["id"]
    db.execute(
        delete(p.allocations).where(
            condition(p.allocations, tenant), p.allocations.c.order_id == key
        )
    )
    db.execute(
        delete(p.accounts).where(
            condition(p.accounts, tenant), p.accounts.c.order_id == key, p.accounts.c.position != 0
        )
    )


def refresh_status(order, active):
    statuses = Counter(line["status"] for line in active)
    if not statuses:
        return "confirmed" if order["status"] != "draft" else "draft"
    if statuses["preparing"]:
        return "preparing"
    if statuses["sent"]:
        return "sent"
    if statuses["new"]:
        return order["status"] if order["status"] == "draft" else "confirmed"
    if statuses["ready"]:
        return "ready"
    return "delivered"


def waiter_name(db, tenant, key):
    if not key:
        return ""
    alias = db.scalar(
        select(m.member_profiles.c.display_name).where(
            m.member_profiles.c.tenant_id == tenant, m.member_profiles.c.user_id == key
        )
    )
    user = db.get(User, key)
    return alias or (user.name if user else "")


def table_name(db, tenant, key):
    if not key:
        return ""
    table = get_row(db, m.tables, tenant, key)
    return table["name"] or table["number"]


def snapshot_line(db, tenant, data, previous=None):
    prior_ids = [item["id"] for item in previous["snapshot"]["modifiers"]] if previous else []
    if (
        previous
        and previous["variant_id"] == data.variant_id
        and sorted(prior_ids) == sorted(data.modifier_ids)
    ):
        if data.quantity > previous["quantity"]:
            calculate(db, tenant, data.item_id, data)
        return {key: previous[key] for key in ("snapshot", "preparation_id", "unit_cents")}
    item, variant, extras, unit = calculate(db, tenant, data.item_id, data, details=True)
    base = item["price_cents"]
    snapshot = {
        "name": item["name"],
        "code": item["code"],
        "base_cents": base,
        "variant": variant["name"] if variant else None,
        "variant_cents": unit - base - sum(extra["price_cents"] for extra in extras),
        "modifiers": [
            {"id": extra["id"], "name": extra["name"], "price_cents": extra["price_cents"]}
            for extra in sorted(
                extras, key=lambda option: (option["position"], option["name"], option["id"])
            )
        ],
    }
    default = db.scalar(
        select(m.settings.c.default_preparation_id).where(m.settings.c.tenant_id == tenant)
    )
    area = previous["preparation_id"] if previous and previous["status"] != "new" else None
    if not area:
        for key in (item["preparation_id"], default):
            if key and get_row(db, m.preparation, tenant, key)["active"]:
                area = key
                break
    snapshot["area"] = get_row(db, m.preparation, tenant, area)["name"] if area else "General"
    return {"snapshot": snapshot, "preparation_id": area, "unit_cents": unit}


def ticket_for_line(db, tenant, key):
    return db.scalar(
        select(p.ticket_lines.c.ticket_id)
        .join(p.tickets, p.tickets.c.id == p.ticket_lines.c.ticket_id)
        .where(
            condition(p.ticket_lines, tenant),
            p.ticket_lines.c.line_id == key,
            p.tickets.c.kind.in_(("initial", "additional", "adjustment")),
        )
        .order_by(p.ticket_lines.c.revision.desc(), p.tickets.c.number.desc())
        .limit(1)
    )


def create_tickets(db, actor, tenant, order, entries, kind, reason=None):
    grouped = defaultdict(list)
    for line, previous in entries:
        grouped[line["preparation_id"]].append((line, previous))
    results = []
    for area, bucket in grouped.items():
        number = next_number(db, tenant, "kitchen")
        ticket = save(
            db,
            p.tickets,
            tenant,
            {
                "order_id": order["id"],
                "preparation_id": area,
                "actor_id": actor.id,
                "number": number,
                "kind": kind,
                "state": "new",
                "snapshot": {
                    "order_number": order["number"],
                    "notes": order["notes"],
                    "reason": reason,
                    "mode": order["mode"],
                    "table": table_name(db, tenant, order["table_id"]),
                    "waiter": waiter_name(db, tenant, order["waiter_id"]),
                    "area": get_row(db, m.preparation, tenant, area)["name"] if area else "General",
                },
            },
        )
        for line, previous in bucket:
            base = {
                "id": line["id"],
                **line["snapshot"],
                "quantity": previous["quantity"] if kind == "cancellation" else line["quantity"],
                "notes": line["notes"],
            }
            base["before"] = (
                {
                    "quantity": previous["quantity"],
                    "notes": previous["notes"],
                    "variant": previous["snapshot"]["variant"],
                    "modifiers": previous["snapshot"]["modifiers"],
                }
                if previous
                else None
            )
            save(
                db,
                p.ticket_lines,
                tenant,
                {
                    "ticket_id": ticket,
                    "line_id": line["id"],
                    "order_id": order["id"],
                    "revision": line["revision"],
                    "state": "new",
                    "snapshot": base,
                    "original_ticket_id": ticket_for_line(db, tenant, line["id"])
                    if previous
                    else None,
                },
            )
        notify(db, actor, tenant, f"pos.kitchen.{kind}", ticket)
        results.append(ticket)
    return results


def retire_line_ticket(db, tenant, key):
    affected = rows(
        db,
        p.ticket_lines,
        tenant,
        p.ticket_lines.c.line_id == key,
        p.ticket_lines.c.state.in_(("new", "preparing")),
        p.ticket_lines.c.ticket_id.in_(
            select(p.tickets.c.id).where(
                condition(p.tickets, tenant),
                p.tickets.c.kind.in_(("initial", "additional", "adjustment")),
            )
        ),
    )
    for entry in affected:
        save(db, p.ticket_lines, tenant, {"state": "cancelled"}, entry["id"])
    for ticket in {row["ticket_id"] for row in affected}:
        entries = rows(db, p.ticket_lines, tenant, p.ticket_lines.c.ticket_id == ticket)
        live = {item["state"] for item in entries} - {"cancelled"}
        if not live:
            save(db, p.tickets, tenant, {"state": "cancelled"}, ticket)
        elif live == {"ready"}:
            save(db, p.tickets, tenant, {"state": "ready", "ready_at": now()}, ticket)


def edit_line(db, actor, access, order, data):
    tenant = access.tenant.id
    previous = get_line(db, tenant, order["id"], data.line_id) if data.line_id else None
    if (data.op == "edit") != bool(previous) or (previous and previous["item_id"] != data.item_id):
        raise HTTPException(422, "Selecciona una línea del platillo")
    sent = previous and previous["status"] != "new"
    if sent and not data.reason:
        raise HTTPException(422, "Indica el motivo del ajuste")
    if sent and previous["status"] in {"preparing", "ready", "delivered"}:
        access.require("kitchen.adjust")
    values = {
        **snapshot_line(db, tenant, data, previous),
        "order_id": order["id"],
        "item_id": data.item_id,
        "variant_id": data.variant_id,
        "quantity": data.quantity,
        "notes": data.notes,
        "revision": previous["revision"] + 1 if previous else 1,
        "status": "sent" if sent else "new",
    }
    if sent:
        values["preparation_id"] = previous["preparation_id"]
        values["snapshot"] = {**values["snapshot"], "area": previous["snapshot"]["area"]}
    key = save(db, p.lines, tenant, values, previous["id"] if previous else None)
    db.execute(
        delete(p.line_modifiers).where(
            condition(p.line_modifiers, tenant), p.line_modifiers.c.line_id == key
        )
    )
    for extra in values["snapshot"]["modifiers"]:
        save(
            db,
            p.line_modifiers,
            tenant,
            {
                "line_id": key,
                "modifier_id": extra["id"],
                "name": extra["name"],
                "price_cents": extra["price_cents"],
            },
        )
    if sent:
        retire_line_ticket(db, tenant, key)
        create_tickets(
            db, actor, tenant, order, [({"id": key, **values}, previous)], "adjustment", data.reason
        )
    return {"line_id": key, "before": previous, "after": values, "reason": data.reason}


def cancel_lines(db, actor, access, order, entries, reason):
    tenant = access.tenant.id
    sent_entries = []
    for line in entries:
        if line["status"] != "new":
            if not reason:
                raise HTTPException(422, "Indica el motivo de la cancelación")
            if line["status"] in {"preparing", "ready", "delivered"}:
                access.require("kitchen.cancel")
            retire_line_ticket(db, tenant, line["id"])
        result = {"status": "cancelled", "revision": line["revision"] + 1}
        save(db, p.lines, tenant, result, line["id"])
        if line["status"] != "new":
            sent_entries.append(({**line, **result, "quantity": 0}, line))
    return create_tickets(db, actor, tenant, order, sent_entries, "cancellation", reason)
