from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.commercial_models import SubscriptionEvent
from app.entitlements import today
from tests.conftest import ORIGIN, login, member, restaurant

P = "/api/platform"


def plan_data(code="business", monthly=19000, **overrides):
    return {
        "code": code,
        "name": "Negocio",
        "monthly_cents": monthly,
        "max_admins": 2,
        "max_staff": 5,
        "max_total": 7,
        "trial_days": 5,
        "grace_days": 3,
        **overrides,
    }


def make_subscription(client, slug, plan="basic", **overrides):
    current = today()
    payload = {
        "restaurant": slug,
        "plan_code": plan,
        "starts_on": current.isoformat(),
        "ends_on": (current + timedelta(days=30)).isoformat(),
        "pending": True,
        **overrides,
    }
    response = client.post(f"{P}/subscriptions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_payment(client, period, amount, **overrides):
    payload = {
        "period_id": period,
        "amount_cents": amount,
        "method": "Efectivo",
        "paid_on": today().isoformat(),
        "request_key": str(uuid4()),
        **overrides,
    }
    result = client.post(f"{P}/payments", json=payload)
    assert result.status_code == 201, result.text
    return result.json()


def test_plan_version_restaurant_and_history(service):
    _, client = service
    assert login(client).status_code == 200
    assert client.post(f"{P}/plans", json=plan_data(max_total=99)).status_code == 422
    assert client.post(f"{P}/plans", json=plan_data()).status_code == 201
    assert client.post(f"{P}/plans", json=plan_data()).status_code == 409
    restaurant(client, "negocio", "business")
    sub = make_subscription(client, "negocio", "business", pending=False)
    assert sub["price_cents"] == 19000 and sub["state"] == "trial"
    update = client.put(f"{P}/plans/business", json=plan_data(monthly=22500))
    assert update.json()["revision"] == 2
    check = client.get(f"{P}/plans/business/versions").json()
    assert [row["monthly_cents"] for row in check] == [22500, 19000]
    assert restaurant(client, "nuevo-negocio", "business")["plan"]["monthly_cents"] == 22500
    saved = client.get(f"{P}/subscriptions/{sub['id']}").json()
    assert saved["price_cents"] == 19000 and saved["revision"] == 1
    profile = client.put(
        f"{P}/restaurants/negocio",
        json={
            "name": "Café de prueba",
            "legal_name": "Comercio SA",
            "tax_id": "100-1",
            "owner": "Titular",
            "contact_email": "admin@example.org",
            "notes": "Observación interna",
        },
    )
    assert profile.json()["legal_name"] == "Comercio SA"
    assert profile.json()["notes"] == "Observación interna"
    assert client.get(f"{P}/restaurants", params={"plan_code": "business"}).json()["total"] == 2
    assert (
        client.post(f"{P}/restaurants/negocio/active", json={"active": False}).json()["active"]
        is False
    )
    assert client.get(f"{P}/restaurants", params={"state": "suspended"}).json()["total"] == 1
    assert (
        client.post(f"{P}/restaurants/negocio/active", json={"active": True}).json()["active"]
        is True
    )
    assert client.delete(f"{P}/plans/business").status_code == 200
    assert not any(row["code"] == "business" for row in client.get(f"{P}/plans").json())
    assert len(client.get(f"{P}/restaurants/negocio/history").json()["activity"]) >= 5
    assert client.get(f"{P}/plan-catalog").json()
    assert client.get(f"{P}/audit", params={"q": "plan.price"}).json()[0]["action"] == "plan.price"


def test_payment_partial_renewal_concurrency_and_exports(service):
    app, client = service
    assert login(client).status_code == 200
    restaurant(client, "cafeteria")
    assert client.get(f"{P}/subscription-restaurants").json()[0]["slug"] == "cafeteria"
    assert len(client.get(f"{P}/subscription-plans").json()) == 2
    sub = make_subscription(client, "cafeteria")
    path = f"{P}/subscriptions/{sub['id']}"
    invalid = client.put(f"{path}/terms", json={"grace_days": 0, "ends_on": sub["starts_on"]})
    assert invalid.status_code == 422
    edited = client.put(
        f"{path}/terms",
        json={
            "grace_days": 3,
            "ends_on": sub["ends_on"],
            "trial_days": 0,
            "discount_cents": 0,
        },
    )
    assert edited.status_code == 200 and edited.json()["grace_days"] == 3
    (initial,) = client.get(f"{path}").json()["periods"]
    key = str(uuid4())
    partial = add_payment(client, initial["id"], 6500, request_key=key, reference="=referencia")
    assert (
        add_payment(client, initial["id"], 6500, request_key=key, reference="=referencia")["id"]
        == partial["id"]
    )
    second = add_payment(client, initial["id"], 8500)
    assert (
        client.put(f"{path}/terms", json={"grace_days": 0, "discount_cents": 0}).status_code == 409
    )
    assert client.put(f"{path}/terms", json={"grace_days": 4}).status_code == 200
    assert (
        client.post(f"{P}/payments/{partial['id']}/state", json={"action": "confirm"}).status_code
        == 200
    )
    current = client.get(path).json()
    assert current["state"] == "pending" and current["periods"][0]["balance_cents"] == 8500
    assert (
        client.post(f"{P}/payments/{second['id']}/state", json={"action": "confirm"}).status_code
        == 200
    )
    assert client.get(path).json()["state"] == "active"
    expiry = today() + timedelta(days=30)
    renewal_payload = {
        "starts_on": expiry.isoformat(),
        "ends_on": (expiry + timedelta(days=30)).isoformat(),
    }
    renewal = client.post(f"{path}/renewals", json=renewal_payload)
    assert renewal.status_code == 201, renewal.text
    period = renewal.json()
    assert client.post(f"{path}/renewals", json=renewal_payload).json()["id"] == period["id"]
    assert len(client.get(f"{P}/payment-subscriptions/{sub['id']}/periods").json()) == 2
    third = add_payment(client, period["id"], 15000)
    fourth = add_payment(client, period["id"], 15000)
    cookies = dict(client.cookies)

    def confirm(payment):
        with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}, cookies=cookies) as other:
            return other.post(f"{P}/payments/{payment['id']}/state", json={"action": "confirm"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, [third, fourth]))
    assert sorted(item.status_code for item in results) == [200, 409]
    confirmed = next(item.json() for item in results if item.status_code == 200)
    assert confirm(confirmed).status_code == 200
    assert client.get(path).json()["ends_on"] == renewal_payload["ends_on"]
    with Session(app.state.engine) as db:
        actions = db.scalars(select(SubscriptionEvent.action)).all()
        assert actions.count("renew") == 1
    csv = client.get(f"{P}/payments-export/csv").text
    assert "'=referencia" in csv
    assert client.get(f"{P}/payments-export/pdf").content.startswith(b"%PDF")
    assert client.get(f"{P}/payments-export/otro").status_code == 404
    result = client.get(f"{P}/commercial-summary").json()
    assert result["collected_cents"] == 30000
    assert result["monthly_recurring_cents"] == 15000
    assert result["annual_projected_cents"] == 180000
    assert client.get(f"{P}/reports").json()["received_month"] == 3
    assert (
        client.post(f"{P}/payments/{confirmed['id']}/state", json={"action": "reverse"}).status_code
        == 200
    )
    assert client.get(path).json()["ends_on"] == expiry.isoformat()


def test_subscription_grace_expiry_and_capacity(service):
    _, client = service
    assert login(client).status_code == 200
    restaurant(client, "gracia", "pro")
    assert member(client, "gracia", "administrador@example.org").status_code == 201
    assert member(client, "gracia", "administrador-dos@example.org").status_code == 201
    on = today()
    sub = make_subscription(
        client,
        "gracia",
        "pro",
        starts_on=(on - timedelta(days=31)).isoformat(),
        ends_on=(on - timedelta(days=1)).isoformat(),
        grace_days=3,
        pending=False,
    )
    assert sub["state"] == "grace"
    url = f"{P}/subscriptions/{sub['id']}"
    assert (
        client.post(f"{url}/plan", json={"plan_code": "basic", "cycle": "monthly"}).status_code
        == 409
    )
    assert client.post(f"{url}/state", json={"action": "suspend"}).json()["state"] == "suspended"
    with TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as tenant:
        assert login(tenant, "administrador@example.org").status_code == 200
        assert tenant.get("/api/restaurants/gracia/dashboard").status_code == 200
        assert tenant.get("/api/restaurants/gracia/members").status_code == 403
        assert client.post(f"{url}/state", json={"action": "resume"}).json()["state"] == "grace"
        assert tenant.get("/api/restaurants/gracia/members").status_code == 200
    restaurant(client, "vencida")
    expired = make_subscription(
        client,
        "vencida",
        ends_on=(on - timedelta(days=4)).isoformat(),
        starts_on=(on - timedelta(days=35)).isoformat(),
        grace_days=2,
        pending=False,
    )
    assert expired["state"] == "expired"
    assert len(client.get(f"{P}/subscriptions", params={"state": "expired"}).json()) == 1


def test_commercial_roles_session_and_last_super(service):
    _, client = service
    assert login(client).status_code == 200
    (first,) = client.get(f"{P}/users").json()
    assert (
        client.put(
            f"{P}/users/{first['id']}",
            json={
                "name": first["name"],
                "role": "auditor",
                "active": True,
            },
        ).status_code
        == 409
    )
    assert client.put(f"{P}/roles/auditor", json={"permissions": ["users"]}).status_code == 422
    assert (
        client.put(f"{P}/roles/auditor", json={"permissions": ["audit", "reports"]}).status_code
        == 200
    )
    assert "audit" in client.get(f"{P}/roles").json()["auditor"]
    result = client.post(
        f"{P}/users",
        json={
            "name": "Auditor autorizado",
            "email": "auditor@example.org",
            "role": "auditor",
            "password": "Contraseña de plataforma",
        },
    )
    assert result.status_code == 201, result.text
    worker = result.json()
    with TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as auditor:
        assert login(auditor, worker["email"], "Contraseña de plataforma").status_code == 200
        assert auditor.get(f"{P}/audit").status_code == 200
        summary = auditor.get(f"{P}/commercial-summary").json()
        assert summary["recent_restaurants"] == [] and summary["backup"] is None
        assert auditor.get(f"{P}/restaurants").status_code == 403
        assert auditor.get(f"{P}/users").status_code == 403
        assert auditor.get(f"{P}/backups").status_code == 403
        (session,) = client.get(f"{P}/users/{worker['id']}/sessions").json()
        revoke_path = f"{P}/users/{worker['id']}/sessions/{session['id']}/revoke"
        assert client.post(revoke_path).status_code == 200
        assert auditor.get(f"{P}/audit").status_code == 401
    assert (
        client.put(
            f"{P}/users/{worker['id']}",
            json={
                "name": worker["name"],
                "role": "support",
                "active": False,
            },
        ).json()["active"]
        is False
    )
