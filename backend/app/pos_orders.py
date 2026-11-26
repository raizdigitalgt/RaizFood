from fastapi import HTTPException
from sqlalchemy import delete

from app import pos_models as p
from app.models import now
from app.pos_service import (
    account_rows,
    applied_discount,
    cancel_lines,
    check_version,
    check_waiter,
    combine_accounts,
    create_tickets,
    edit_line,
    free_table,
    get_line,
    mark_table,
    open_lines,
    pos_config,
    refresh_status,
    save,
    split_account,
    totals,
    trace,
)
from app.restaurant_records import condition, get_row

RIGHTS = {
    "add": "orders.update",
    "edit": "orders.update",
    "remove": "orders.update",
    "confirm": "orders.update",
    "details": "orders.update",
    "delivery": "orders.update",
    "send": "kitchen.tickets.create",
    "bill": "orders.request_bill",
    "deliver": "orders.update",
    "merge": "orders.merge",
    "split": "orders.split",
    "reopen_bill": "orders.request_bill",
    "cancel": "orders.cancel",
    "transfer": "orders.transfer",
    "discount": "orders.discount",
}
AFTER_BILL = {"cancel", "transfer", "split", "merge", "bill", "reopen_bill", "deliver", "delivery"}


def apply_discount(db, actor, tenant, order, data):
    line = get_line(db, tenant, order["id"], data.line_id) if data.line_id else None
    active = [line] if line else open_lines(db, tenant, order["id"])
    gross = sum(row["unit_cents"] * row["quantity"] for row in active)
    config = pos_config(db, tenant)
    if (
        data.kind == "percent"
        and data.value > config.max_discount_bps
        or data.kind == "fixed"
        and data.value > gross
    ):
        raise HTTPException(422, "El descuento supera el límite permitido")
    match = (
        condition(p.discounts, tenant)
        & (p.discounts.c.order_id == order["id"])
        & (p.discounts.c.line_id == data.line_id)
    )
    db.execute(delete(p.discounts).where(match))
    if data.value:
        rule = {
            "order_id": order["id"],
            "line_id": data.line_id,
            "actor_id": actor.id,
            "kind": data.kind,
            "value": data.value,
            "reason": data.reason,
        }
        save(db, p.discounts, tenant, rule)
        summary, _ = totals(db, tenant, order, open_lines(db, tenant, order["id"]))
        if summary["discount_cents"] > config.max_discount_cents or summary[
            "discount_cents"
        ] > applied_discount(
            summary["subtotal_cents"],
            {
                "kind": "percent",
                "value": config.max_discount_bps,
            },
        ):
            raise HTTPException(422, "El total de descuentos supera la política del restaurante")
    return {"line_id": data.line_id, "kind": data.kind, "value": data.value, "reason": data.reason}


def mutate_order(db, actor, access, key, data):
    tenant = access.tenant.id
    order = get_row(db, p.orders, tenant, key)
    check_version(order, data.version)
    op = data.op
    if order["status"] == "cancelled" or order["financial_status"] not in {
        "unpaid",
        "bill_requested",
    }:
        raise HTTPException(409, "El pedido no acepta cambios")
    if (
        order["status"] == "delivered"
        and order["mode"] != "dine_in"
        and op in {"add", "edit", "remove", "send"}
    ):
        raise HTTPException(409, "La entrega ya está registrada")
    if order["financial_status"] == "bill_requested" and op not in AFTER_BILL:
        raise HTTPException(409, "Reabre la cuenta antes de editar productos o descuentos")
    if op in {"add", "edit", "remove"} and len(account_rows(db, tenant, key)) > 1:
        raise HTTPException(409, "Combina las cuentas antes de modificar productos")
    changes = {}
    patch = {}
    tickets = []
    if op in {"add", "edit"}:
        changes = edit_line(db, actor, access, order, data)
    elif op in {"remove", "cancel"}:
        entries = (
            [get_line(db, tenant, key, data.line_id)]
            if op == "remove"
            else open_lines(db, tenant, key)
        )
        tickets = cancel_lines(db, actor, access, order, entries, data.reason)
        changes = {"before": entries, "reason": data.reason, "tickets": tickets}
        if op == "cancel":
            combine_accounts(db, tenant, order)
            patch.update(status="cancelled", financial_status="unpaid", shipping_cents=0)
            mark_table(db, actor, tenant, order["table_id"], "available")
    elif op == "confirm":
        if order["status"] != "draft" or not open_lines(db, tenant, key):
            raise HTTPException(409, "Confirma un borrador con productos")
        patch["status"] = "confirmed"
    elif op == "send":
        new = [line for line in open_lines(db, tenant, key) if line["status"] == "new"]
        if not new:
            return {"id": key, "version": order["version"], "tickets": []}
        previous = db_has_tickets(db, tenant, key)
        tickets = create_tickets(
            db,
            actor,
            tenant,
            order,
            [(line, None) for line in new],
            "additional" if previous else "initial",
        )
        for line in new:
            save(db, p.lines, tenant, {"status": "sent"}, line["id"])
        changes = {"tickets": tickets, "lines": [line["id"] for line in new]}
    elif op == "details":
        waiter_id = data.waiter_id if "waiter_id" in data.model_fields_set else order["waiter_id"]
        if waiter_id != order["waiter_id"]:
            access.require("orders.assign")
            check_waiter(db, access, actor, waiter_id)
        patch.update(notes=data.notes, waiter_id=waiter_id)
        changes = {"before": {field: order[field] for field in patch}, "after": patch.copy()}
    elif op == "bill":
        active = open_lines(db, tenant, key)
        if not active or any(line["status"] == "new" for line in active):
            raise HTTPException(409, "Envía los productos antes de solicitar la cuenta")
        patch["financial_status"] = "bill_requested"
        mark_table(db, actor, tenant, order["table_id"], "payment_due")
    elif op == "reopen_bill":
        if order["financial_status"] != "bill_requested":
            raise HTTPException(409, "El pedido no tiene la cuenta solicitada")
        patch["financial_status"] = "unpaid"
        mark_table(db, actor, tenant, order["table_id"], "occupied")
    elif op == "deliver":
        if order["status"] != "ready":
            raise HTTPException(409, "Espera a que estén listos todos los productos")
        for line in open_lines(db, tenant, key):
            if line["status"] == "ready":
                save(db, p.lines, tenant, {"status": "delivered"}, line["id"])
    elif op == "delivery":
        transitions = {"pending": "en_route", "en_route": "delivered"}
        if (
            order["mode"] != "delivery"
            or order["status"] != "delivered"
            or transitions.get(order["delivery_state"]) != data.state
        ):
            raise HTTPException(409, "El pedido aún no puede avanzar a esa etapa de entrega")
        patch["delivery_state"] = data.state
    elif op == "transfer":
        if order["mode"] != "dine_in" or data.table_id == order["table_id"]:
            raise HTTPException(422, "Selecciona otra mesa")
        free_table(db, tenant, data.table_id)
        before = order["table_id"]
        mark_table(db, actor, tenant, before, "available")
        mark_table(
            db,
            actor,
            tenant,
            data.table_id,
            "payment_due" if order["financial_status"] == "bill_requested" else "occupied",
        )
        patch.update(table_id=data.table_id, seated_at=now())
        active = [
            line
            for line in open_lines(db, tenant, key)
            if line["status"] in {"sent", "preparing", "ready"}
        ]
        tickets = create_tickets(
            db,
            actor,
            tenant,
            {**order, **patch},
            [(line, line) for line in active],
            "transfer",
            data.reason,
        )
        changes = {
            "before": before,
            "after": data.table_id,
            "reason": data.reason,
            "tickets": tickets,
        }
    elif op == "split":
        changes = split_account(db, tenant, order, data)
    elif op == "merge":
        changes = {"before": account_rows(db, tenant, key)}
        combine_accounts(db, tenant, order)
    elif op == "discount":
        changes = apply_discount(db, actor, tenant, order, data)
    active = open_lines(db, tenant, key)
    patch.setdefault("status", refresh_status(order, active))
    summary, _ = totals(db, tenant, {**order, **patch}, active)
    patch.update(**summary, version=order["version"] + 1)
    save(db, p.orders, tenant, patch, key)
    if patch["status"] != order["status"]:
        changes["status"] = {"before": order["status"], "after": patch["status"]}
    if patch.get("financial_status"):
        changes["financial_status"] = {
            "before": order["financial_status"],
            "after": patch["financial_status"],
        }
    if op == "discount":
        changes["discount_cents"] = {
            "before": order["discount_cents"],
            "after": patch["discount_cents"],
        }
    trace(db, actor, tenant, key, op, changes)
    return {"id": key, "version": patch["version"], "tickets": tickets}


def db_has_tickets(db, tenant, key):
    from sqlalchemy import select

    return db.scalar(
        select(p.tickets.c.id)
        .where(
            condition(p.tickets, tenant),
            p.tickets.c.order_id == key,
            p.tickets.c.kind.in_(("initial", "additional")),
        )
        .limit(1)
    )
