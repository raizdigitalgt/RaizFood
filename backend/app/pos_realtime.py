from asyncio import wait_for

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import pos_models as p
from app.access import access_for
from app.auth import credentials
from app.models import AuditLog
from app.pos_kitchen import authorized_areas

router = APIRouter()
SCOPES = {"orders.view", "tables.view", "kitchen.view", "pos.access", "reports.operational"}
POLL_SECONDS = 1


def subscribe(socket, slug, previous):
    with Session(socket.app.state.engine) as db:
        session, actor = credentials(socket, db)
        access = access_for(db, actor, session.tenant_id)
        if not access or access.tenant.slug != slug or not access.permissions & SCOPES:
            raise HTTPException(403, "Canal no disponible")
        cursor = literal_column("audit_logs.rowid")
        events = select(cursor, AuditLog.action, AuditLog.subject).where(
            AuditLog.tenant_id == access.tenant.id
        )
        if previous is None:
            newest = db.execute(events.order_by(cursor.desc()).limit(1)).first()
            return (newest[0] if newest else 0), []
        current = previous
        changed = set()
        allowed = (
            authorized_areas(db, access, actor) if "kitchen.view" in access.permissions else set()
        )
        for last, action, subject in db.execute(
            events.where(cursor > previous).order_by(cursor).limit(200)
        ):
            current = last
            if (
                action.startswith("pos.order.")
                and {"orders.view", "pos.access", "reports.operational"} & access.permissions
            ):
                changed.add("order." + action.removeprefix("pos.order."))
            elif action.startswith(("pos.table.", "restaurant.tables.", "restaurant.areas.")) and (
                {"tables.view", "reports.operational"} & access.permissions
            ):
                changed.add("table.updated")
            elif action.startswith("pos.kitchen."):
                order_scopes = {"orders.view", "reports.operational"} & access.permissions
                if order_scopes or (
                    "kitchen.view" in access.permissions
                    and (
                        allowed is None
                        or db.scalar(
                            select(p.tickets.c.id).where(
                                p.tickets.c.tenant_id == access.tenant.id,
                                p.tickets.c.id == subject,
                                p.tickets.c.preparation_id.in_(allowed),
                            )
                        )
                    )
                ):
                    kind = action.removeprefix("pos.kitchen.")
                    event = {
                        "initial": "created",
                        "additional": "created",
                        "cancellation": "cancelled",
                    }
                    changed.add("kitchen_ticket." + event.get(kind, "updated"))
            elif action in {"pos.settings.updated", "restaurant.settings.edit"}:
                changed.add("pos.settings_changed")
            elif action.startswith(
                (
                    "restaurant.items.",
                    "restaurant.categories.",
                    "restaurant.variants.",
                    "restaurant.groups.",
                    "restaurant.modifiers.",
                    "restaurant.menu.",
                )
            ):
                if {"pos.access", "orders.view"} & access.permissions:
                    changed.add("menu.availability_changed")
        return current, sorted(changed)


@router.websocket("/restaurants/{slug}/events")
async def live(socket: WebSocket, slug: str):
    if (
        socket.headers.get("origin") != socket.app.state.settings.frontend_url.rstrip("/")
        or socket.app.state.settings.maintenance_mode
    ):
        await socket.close(1008)
        return
    try:
        cursor, _ = await run_in_threadpool(subscribe, socket, slug, None)
        await socket.accept()
        await socket.send_json({"type": "sync", "events": []})
        while True:
            try:
                message = await wait_for(socket.receive(), timeout=POLL_SECONDS)
                if message["type"] == "websocket.disconnect":
                    return
                await socket.close(1008)
                return
            except TimeoutError:
                cursor, events = await run_in_threadpool(subscribe, socket, slug, cursor)
                if events:
                    await socket.send_json({"type": "changed", "events": events})
    except HTTPException:
        await socket.close(1008)
    except WebSocketDisconnect:
        return
