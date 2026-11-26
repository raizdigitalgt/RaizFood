from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.models import User
from tests.conftest import NORTH, ORIGIN, SOUTH, login, member
from tests.test_restaurant import create, replace

SLUG = "norte-fase3"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def order(client, table=None, *, status=201, **fields):
    body = {"request_id": str(uuid4()), "mode": "dine_in", "table_id": table, **fields}
    return ok(client.post(f"{NORTH}/orders", json=body), status)


def detail(client, key):
    return ok(client.get(f"{NORTH}/orders/{key}"))


def command(client, current, op, status=200, **fields):
    body = {"request_id": str(uuid4()), "version": current["version"], "op": op, **fields}
    return ok(client.post(f"{NORTH}/orders/{current['id']}/actions", json=body), status)


def move(client, ticket, state, status=200, **fields):
    body = {
        "request_id": str(uuid4()),
        "version": ticket["order_version"],
        "state": state,
        **fields,
    }
    return ok(client.post(f"{NORTH}/kitchen/tickets/{ticket['id']}/state", json=body), status)


def staff(app, platform, role):
    client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    email = f"{role}@pos-test.example.org"
    ok(member(platform, SLUG, email, role), 201)
    ok(login(client, email))
    with Session(app.state.engine) as db:
        return client, db.scalar(select(User.id).where(User.email == email))


@pytest.fixture
def setup(tenants):
    _, _, client, _ = tenants
    area = create(client, "areas", {"name": "Terraza"})
    tables = [
        create(
            client,
            "tables",
            {"number": str(index), "area_id": area["id"], "capacity": 4, "position": index},
        )
        for index in range(1, 4)
    ]
    kitchen = create(client, "preparation", {"name": "Parrilla"})
    bar = create(client, "preparation", {"name": "Bar"})
    category = create(client, "categories", {"name": "Servicio"})
    group = create(client, "groups", {"name": "Opciones", "minimum": 1, "maximum": 2})
    extra = create(
        client, "modifiers", {"name": "Salsa", "group_id": group["id"], "price_cents": 50}
    )
    dish_fields = {
        "name": "Taco",
        "code": "TC1",
        "category_id": category["id"],
        "price_cents": 1001,
        "group_ids": [group["id"]],
        "preparation_id": kitchen["id"],
    }
    taco = create(client, "items", dish_fields)
    variant = create(
        client,
        "variants",
        {
            "item_id": taco["id"],
            "name": "Grande",
            "code": "TC2",
            "pricing": "adjust",
            "price_cents": 300,
        },
    )
    drink = create(
        client,
        "items",
        {
            "name": "Limonada",
            "code": "LIM",
            "category_id": category["id"],
            "price_cents": 299,
            "preparation_id": bar["id"],
        },
    )
    return tables, kitchen, bar, taco, drink, variant, extra, dish_fields


def test_pos_waiter_kitchen_transfer_accounts_and_live(tenants, setup):
    app, platform, admin, south = tenants
    tables, kitchen, bar, taco, drink, variant, extra, _ = setup
    waiter, _ = staff(app, platform, "waiter")
    cook, cook_id = staff(app, platform, "cook")
    cashier, _ = staff(app, platform, "cashier")
    with closing(waiter), closing(cook), closing(cashier):
        stations = f"{NORTH}/pos/stations/{cook_id}"
        assert ok(admin.put(stations, json={"preparation_ids": [kitchen["id"]]})) == {
            "preparation_ids": [kitchen["id"]]
        }
        assert ok(admin.get(stations))["preparation_ids"] == [kitchen["id"]]
        modes = ok(admin.get(f"{NORTH}/settings"))
        assert ok(
            admin.put(
                f"{NORTH}/settings",
                json={**modes, "order_modes": ["dine_in", "takeaway", "delivery"]},
            )
        )["order_modes"] == ["dine_in", "takeaway", "delivery"]
        opened = order(waiter, tables[0]["id"], notes="Servicio especial", guests=2)
        key = opened["id"]
        assert opened["version"] == 1
        assert order(waiter, tables[0]["id"], status=409)
        board = ok(waiter.get(f"{NORTH}/service-tables"))
        assert (board[0]["state"], board[0]["order_id"]) == ("occupied", key)
        area_id = tables[0]["area_id"]
        assert admin.delete(f"{NORTH}/records/areas/{area_id}").status_code == 409
        assert (
            replace(admin, "areas", area_id, {"name": "Terraza", "active": False}).status_code
            == 409
        )
        filters = ok(waiter.get(f"{NORTH}/orders/filters"))
        assert filters["tables"][0]["id"] == tables[0]["id"] and len(filters["waiters"]) == 1
        assert (
            ok(admin.get(f"{NORTH}/orders", params={"q": "Servicio", "mode": "dine_in"}))["total"]
            == 1
        )
        assert ok(south.get(f"{SOUTH}/orders"))["total"] == 0
        assert south.get(f"{SOUTH}/orders/{key}").status_code == 404
        assert south.get(f"{NORTH}/orders/{key}").status_code == 404
        assert cook.get(f"{NORTH}/orders").status_code == 403
        command(cashier, opened, "add", 403, item_id=drink["id"])
        command(waiter, opened, "discount", 403, kind="fixed", value=1, reason="Prueba")
        command(waiter, opened, "add", 422, item_id=taco["id"])
        added = command(
            waiter,
            opened,
            "add",
            item_id=taco["id"],
            quantity=2,
            variant_id=variant["id"],
            modifier_ids=[extra["id"]],
            notes="Sin cebolla",
        )
        added = command(waiter, added, "add", item_id=drink["id"])
        confirmed = command(waiter, added, "confirm")
        assert detail(waiter, key)["status"] == "confirmed"
        with cook.websocket_connect(f"wss://raizfood.test{NORTH}/events") as channel:
            assert channel.receive_json()["type"] == "sync"
            sent = command(waiter, confirmed, "send")
            assert channel.receive_json() == {
                "type": "changed",
                "events": ["kitchen_ticket.created"],
            }
        assert len(sent["tickets"]) == 2
        assert command(waiter, sent, "send") == {
            "id": key,
            "version": sent["version"],
            "tickets": [],
        }
        tickets = ok(cook.get(f"{NORTH}/kitchen"))["tickets"]
        assert len(tickets) == 1 and tickets[0]["snapshot"]["area"] == "Parrilla"
        assert tickets[0]["items"][0]["snapshot"]["notes"] == "Sin cebolla"
        assert ok(cook.get(f"{NORTH}/kitchen", params={"area": bar["id"]}))["tickets"] == []
        other = next(ticket for ticket in sent["tickets"] if ticket != tickets[0]["id"])
        assert cook.get(f"{NORTH}/kitchen/tickets/{other}").status_code == 404
        move(cook, tickets[0], "ready", 409)
        move(cook, tickets[0], "preparing")
        move(cook, tickets[0], "preparing", 409)
        ticket = ok(cook.get(f"{NORTH}/kitchen"))["tickets"][0]
        move(cook, ticket, "ready", ticket_line_id=ticket["items"][0]["id"])
        all_tickets = ok(admin.get(f"{NORTH}/kitchen"))["tickets"]
        move(admin, next(ticket for ticket in all_tickets if ticket["id"] == other), "preparing")
        move(
            admin,
            next(
                ticket
                for ticket in ok(admin.get(f"{NORTH}/kitchen"))["tickets"]
                if ticket["id"] == other
            ),
            "ready",
        )
        ready = detail(waiter, key)
        assert ready["status"] == "ready"
        assert ready["lines"][0]["unit_cents"] == 1351
        second = command(waiter, ready, "add", item_id=drink["id"], notes="Con hielo")
        second = command(waiter, second, "send")
        ticket = ok(admin.get(f"{NORTH}/kitchen/tickets/{second['tickets'][0]}"))
        assert ticket["kind"] == "additional" and len(ticket["items"]) == 1
        assert ticket["items"][0]["snapshot"]["notes"] == "Con hielo"
        shifted = command(admin, second, "transfer", table_id=tables[1]["id"], reason="Petición")
        assert len(shifted["tickets"]) == 2
        room = ok(admin.get(f"{NORTH}/service-tables"))
        assert [(table["state"], table["order_id"]) for table in room[:2]] == [
            ("available", None),
            ("occupied", key),
        ]
        discounted = command(admin, shifted, "discount", kind="fixed", value=1, reason="Atención")
        split = command(
            cashier,
            discounted,
            "split",
            name="Invitado",
            items=[{"line_id": ready["lines"][0]["id"], "quantity": 1}],
        )
        divided = detail(cashier, key)
        assert sum(account["total_cents"] for account in divided["accounts"]) == 3299
        assert sum(account["discount_cents"] for account in divided["accounts"]) == 1
        assert len(divided["accounts"]) == 2
        assert split["tickets"] == []
        assert "PRELIMINAR" in ok(cashier.get(f"{NORTH}/orders/{key}/bill"))["disclaimer"]
        combined = command(cashier, split, "merge")
        bill = command(cashier, combined, "bill")
        assert detail(cashier, key)["financial_status"] == "bill_requested"
        assert ok(admin.get(f"{NORTH}/service-tables"))[1]["state"] == "payment_due"
        assert command(waiter, bill, "add", 409, item_id=drink["id"])
        command(waiter, bill, "reopen_bill")
        assert len(detail(waiter, key)["accounts"]) == 1
        assert "transfer" in {
            row["action"] for row in ok(waiter.get(f"{NORTH}/orders/{key}/history"))
        }
        assert ok(admin.get(f"{NORTH}/operational-summary"))["today"] == 1
        with pytest.raises(WebSocketDisconnect):
            with south.websocket_connect(f"wss://raizfood.test{NORTH}/events"):
                pass
        with pytest.raises(WebSocketDisconnect):
            with cook.websocket_connect(
                f"{NORTH}/events", headers={"Origin": "https://other.invalid"}
            ):
                pass


def test_pos_historical_adjustments_policy_and_delivery(tenants, setup):
    app, platform, admin, _ = tenants
    tables, _, _, taco, drink, variant, extra, fields = setup
    pos = f"{NORTH}/pos/config"
    assert ok(admin.get(pos))["kitchen_warning_minutes"] == 15
    ok(
        admin.put(
            pos,
            json={
                "kitchen_warning_minutes": 3,
                "max_discount_bps": 2500,
                "max_discount_cents": 200,
            },
        )
    )
    settings = ok(admin.get(f"{NORTH}/settings"))
    ok(
        admin.put(
            f"{NORTH}/settings",
            json={**settings, "order_modes": ["takeaway", "delivery", "dine_in"]},
        )
    )
    assert ok(admin.get(pos))["kitchen_warning_minutes"] == 3
    waiter, _ = staff(app, platform, "waiter")
    with closing(waiter):
        order(admin, mode="delivery", status=422, name="Cliente")
        order(admin, tables[2]["id"], mode="takeaway", status=422)
        order(admin, mode="takeaway", name="Retiro")
        shipping = order(
            waiter,
            mode="delivery",
            name="Cliente",
            address="Avenida",
            phone="5555",
            shipping_cents=151,
            reference="Local",
            estimated_at=1810000000,
        )
        key = shipping["id"]
        added = command(
            waiter,
            shipping,
            "add",
            item_id=taco["id"],
            variant_id=variant["id"],
            modifier_ids=[extra["id"]],
            quantity=2,
        )
        live = detail(waiter, key)
        assert live["contact"]["reference"] == "Local" and live["total_cents"] == 2853
        assert (
            ok(replace(admin, "items", taco["id"], {**fields, "price_cents": 3209}))["price_cents"]
            == 3209
        )
        sent = command(waiter, added, "send")
        queue = ok(admin.get(f"{NORTH}/kitchen"))["tickets"]
        started = move(admin, queue[0], "preparing")
        current = {**sent, "version": started["version"]}
        line = live["lines"][0]
        patch = {
            "item_id": taco["id"],
            "line_id": line["id"],
            "variant_id": variant["id"],
            "modifier_ids": [extra["id"]],
            "quantity": 1,
            "notes": "Cambio",
        }
        command(waiter, current, "edit", 422, **patch)
        command(waiter, current, "edit", 403, **patch, reason="Cliente cambió")
        adjusted = command(admin, current, "edit", **patch, reason="Cliente cambió")
        saved = detail(admin, key)
        assert saved["lines"][0]["unit_cents"] == 1351
        assert [ticket["kind"] for ticket in ok(admin.get(f"{NORTH}/orders/{key}/tickets"))] == [
            "initial",
            "adjustment",
        ]
        add = command(admin, adjusted, "add", item_id=drink["id"])
        removed = command(admin, add, "remove", line_id=line["id"], reason="Cliente cambió")
        cancel_ticket = ok(admin.get(f"{NORTH}/kitchen/tickets/{removed['tickets'][0]}"))
        assert cancel_ticket["snapshot"]["reason"] == "Cliente cambió"
        assert cancel_ticket["items"][0]["snapshot"]["quantity"] == 1
        assert cancel_ticket["items"][0]["original_ticket_id"]
        command(admin, removed, "discount", 422, kind="percent", value=5000, reason="Límite")
        command(admin, removed, "discount", 422, kind="fixed", value=500, reason="Monto")
        fixed = command(admin, removed, "discount", kind="percent", value=1000, reason="Válido")
        sent = command(admin, fixed, "send")
        command(admin, sent, "delivery", 409, state="en_route")
        current = ok(admin.get(f"{NORTH}/kitchen"))["tickets"]
        route = next(ticket for ticket in current if ticket["id"] == sent["tickets"][0])
        move(admin, route, "preparing")
        route = next(
            ticket
            for ticket in ok(admin.get(f"{NORTH}/kitchen"))["tickets"]
            if ticket["id"] == sent["tickets"][0]
        )
        move(admin, route, "ready")
        delivered = command(waiter, detail(waiter, key), "deliver")
        en_route = command(waiter, delivered, "delivery", state="en_route")
        command(waiter, en_route, "delivery", state="delivered")
        final = detail(waiter, key)
        assert final["delivery_state"] == "delivered" and final["total_cents"] == 420
        room_order = order(admin, tables[2]["id"])
        command(admin, room_order, "cancel", reason="Servicio cancelado")
        assert ok(admin.get(f"{NORTH}/service-tables"))[2]["state"] == "available"


def test_pos_concurrency_and_idempotency(tenants, setup):
    app, _, admin, _ = tenants
    tables, _, _, _, drink, _, _, _ = setup

    def parallel(path, bodies):
        def post(body):
            with closing(
                TestClient(
                    app, base_url=ORIGIN, headers={"Origin": ORIGIN}, cookies=dict(admin.cookies)
                )
            ) as client:
                return client.post(path, json=body)

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(post, bodies))

    body = {"request_id": str(uuid4()), "mode": "dine_in", "table_id": tables[0]["id"]}
    url = f"{NORTH}/orders"
    attempt = parallel(url, [body, {**body, "request_id": str(uuid4())}])
    assert sorted(response.status_code for response in attempt) == [201, 409]
    created = ok(admin.get(f"{url}?active=true"))["items"][0]
    key = created["id"]
    assert created["number"] == 1
    duplicate = parallel(url, [body, body])
    assert all(response.status_code in {201, 409} for response in duplicate)
    repeatable = {**body, "request_id": str(uuid4()), "table_id": tables[1]["id"]}
    duplicates = parallel(url, [repeatable, repeatable])
    assert [item.status_code for item in duplicates] == [201, 201]
    assert duplicates[0].json() == duplicates[1].json()
    assert ok(admin.get(f"{url}?q=2"))["total"] == 1
    assert admin.post(url, json={**repeatable, "notes": "No coincide"}).status_code == 409
    action = {"request_id": str(uuid4()), "version": 1, "op": "add", "item_id": drink["id"]}
    command_url = f"{url}/{key}/actions"
    changes = parallel(command_url, [action, {**action, "request_id": str(uuid4())}])
    assert sorted(response.status_code for response in changes) == [200, 409]
    current = detail(admin, key)
    assert current["version"] == 2 and len(current["lines"]) == 1
    send = {"op": "send", "request_id": str(uuid4()), "version": 2}
    duplicates = parallel(command_url, [send, send])
    assert [item.status_code for item in duplicates] == [200, 200]
    assert duplicates[0].json() == duplicates[1].json()
    assert len(ok(admin.get(f"{url}/{key}/tickets"))) == 1
    bad = {**send, "op": "merge"}
    assert admin.post(command_url, json=bad).status_code == 409

    second = ok(admin.get(f"{url}?q=2"))["items"][0]
    current = detail(admin, key)
    stop = tables[2]["id"]

    def transfer(source):
        with closing(
            TestClient(
                app, base_url=ORIGIN, headers={"Origin": ORIGIN}, cookies=dict(admin.cookies)
            )
        ) as client:
            return client.post(
                f"{url}/{source['id']}/actions",
                json={
                    "op": "transfer",
                    "request_id": str(uuid4()),
                    "table_id": stop,
                    "version": source["version"],
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(transfer, [current, second]))
    assert sorted(response.status_code for response in outcomes) == [200, 409]
    occupied = ok(admin.get(f"{NORTH}/service-tables"))
    assert sum(table["order_id"] is not None for table in occupied) == 2
    assert occupied[2]["order_id"] in {key, second["id"]}


def test_pos_permissions_configuration_and_user_events(tenants, setup):
    app, platform, admin, south = tenants
    tables, kitchen, _, _, drink, _, _, _ = setup
    room = tables[0]["area_id"]
    north_opts = f"{NORTH}/pos/options"
    customer = create(
        admin, "customers", {"name": "Ana Servicio", "phone": "5555", "address": "Calle 1"}
    )
    archived = create(admin, "customers", {"name": "Inactivo", "active": False})
    external = create(south, "customers", {"name": "Otra sede"}, base=SOUTH)
    waiter, waiter_id = staff(app, platform, "waiter")
    cook, cook_id = staff(app, platform, "cook")
    with closing(waiter), closing(cook):
        assert cook.get(north_opts).status_code == 403
        assert len(ok(admin.get(north_opts))["station_staff"]) == 2
        assert ok(waiter.get(north_opts, params={"customer": "ana"}))["customers"] == [
            {"id": customer["id"], "name": "Ana Servicio"}
        ]
        assert ok(waiter.get(north_opts))["waiters"][0]["id"] == waiter_id
        assert ok(cook.get(f"{NORTH}/kitchen?area=general"))["tickets"] == []
        assert admin.get(f"{NORTH}/pos/stations/{uuid4()}").status_code == 404
        assert (
            admin.put(f"{NORTH}/pos/stations/{waiter_id}", json={"preparation_ids": []}).status_code
            == 404
        )
        assert ok(
            admin.put(
                f"{NORTH}/pos/stations/{cook_id}",
                json={"preparation_ids": [kitchen["id"], kitchen["id"]]},
            )
        )["preparation_ids"] == [kitchen["id"]]
        ok(admin.put(f"{NORTH}/pos/stations/{cook_id}", json={"preparation_ids": []}))
        order(admin, mode="delivery", status=422)
        order(admin, status=422)
        order(admin, tables[0]["id"], status=404, customer_id=external["id"])
        order(admin, tables[0]["id"], status=422, customer_id=archived["id"])
        order(admin, tables[0]["id"], status=404, waiter_id=cook_id)
        order(admin, tables[0]["id"], status=422, shipping_cents=1)

        with waiter.websocket_connect(f"wss://raizfood.test{NORTH}/events") as channel:
            assert channel.receive_json()["type"] == "sync"
            create(admin, "categories", {"name": "En vivo"})
            assert channel.receive_json()["events"] == ["menu.availability_changed"]
            started = order(admin, tables[0]["id"], customer_id=customer["id"], waiter_id=waiter_id)
            assert channel.receive_json()["events"] == ["order.created", "table.updated"]
            channel.send_json({"unrecognized": True})
            with pytest.raises(WebSocketDisconnect):
                channel.receive_json()

        key = started["id"]
        assert detail(waiter, key)["contact"]["phone"] == "5555"
        assert (
            ok(
                admin.get(
                    f"{NORTH}/orders",
                    params={
                        "q": "Ana",
                        "user_id": waiter_id,
                        "table_id": tables[0]["id"],
                        "after": 0,
                        "before": 4102444800,
                        "status": "draft",
                    },
                )
            )["total"]
            == 1
        )
        command(waiter, started, "bill", 409)
        command(waiter, started, "confirm", 409)
        command(waiter, started, "reopen_bill", 409)
        command(waiter, started, "deliver", 409)
        command(admin, started, "transfer", 422, table_id=tables[0]["id"])
        command(waiter, started, "details", 403, notes="Cambio", waiter_id=None)
        updated = command(waiter, started, "details", notes="Una sola cuenta")
        assert detail(waiter, key)["waiter_id"] == waiter_id
        line = command(waiter, updated, "add", item_id=drink["id"], quantity=2)
        line_id = detail(waiter, key)["lines"][0]["id"]
        command(
            admin,
            line,
            "split",
            404,
            name="Cuenta externa",
            source_id=str(uuid4()),
            items=[{"line_id": line_id, "quantity": 1}],
        )
        command(
            admin, line, "split", 422, name="Demasiado", items=[{"line_id": line_id, "quantity": 3}]
        )
        command(admin, line, "split", 422, name="Todo", items=[{"line_id": line_id, "quantity": 2}])
        split = command(
            admin, line, "split", name="Invitado", items=[{"line_id": line_id, "quantity": 1}]
        )
        command(waiter, split, "add", 409, item_id=drink["id"])
        a = detail(admin, key)["accounts"][1]
        command(
            admin,
            split,
            "split",
            422,
            name="Todo el resto",
            source_id=a["id"],
            items=[{"line_id": line_id, "quantity": 1}],
        )
        restored = command(admin, split, "merge")
        no_discount = command(
            admin,
            restored,
            "discount",
            line_id=line_id,
            kind="fixed",
            value=0,
            reason="Sin descuento",
        )
        removed = command(waiter, no_discount, "remove", line_id=line_id)
        assert detail(admin, key)["total_cents"] == 0
        command(waiter, removed, "remove", 404, line_id=line_id)
        assert cook.get(f"{NORTH}/orders/{key}/tickets").status_code == 404
        command(admin, removed, "cancel", reason="Fin del servicio")
        assert admin.delete(f"{NORTH}/records/areas/{room}").status_code == 204
