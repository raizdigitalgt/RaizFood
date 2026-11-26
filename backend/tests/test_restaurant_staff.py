from contextlib import closing
from datetime import timedelta

from fastapi.testclient import TestClient

from app import platform_admin
from app.entitlements import today
from tests.conftest import NORTH, ORIGIN, PASSWORD, SOUTH, login, member
from tests.test_commercial import make_subscription


def test_custom_roles_staff_limits_and_revocation(tenants):
    app, platform, north, south = tenants
    staff = north.get(f"{NORTH}/staff").json()
    (admin,) = staff["items"]
    assert admin["last_access"] is not None and staff["limits"]["max_admins"] == 1
    assert (
        north.put(
            f"{NORTH}/staff/{admin['id']}",
            json={
                "display_name": "Administrador local",
                "role_code": "admin",
                "active": False,
            },
        ).status_code
        == 409
    )
    assert (
        north.post(
            f"{NORTH}/roles", json={"name": "Plataforma", "permissions": ["platform.users"]}
        ).status_code
        == 403
    )
    assert (
        north.post(f"{NORTH}/roles", json={"name": "FEL", "permissions": ["fel.issue"]}).status_code
        == 403
    )
    assert (
        north.put(f"{NORTH}/roles/admin", json={"name": "Admin", "permissions": []}).status_code
        == 403
    )
    made = north.post(
        f"{NORTH}/roles",
        json={"name": "Lectura de clientes", "permissions": ["dashboard.view", "customers.view"]},
    )
    assert made.status_code == 201, made.text
    role = made.json()
    assert (
        north.post(
            f"{NORTH}/roles",
            json={"name": "LECTURA DE CLIENTES", "permissions": ["dashboard.view"]},
        ).status_code
        == 409
    )
    assert (
        north.put(
            f"{NORTH}/roles/{role['code']}",
            json={
                "name": "Lectura autorizada",
                "permissions": ["dashboard.view", "customers.view"],
            },
        ).status_code
        == 200
    )
    assert (
        south.put(
            f"{SOUTH}/roles/{role['code']}",
            json={
                "name": "Cruce",
                "permissions": ["dashboard.view"],
            },
        ).status_code
        == 404
    )
    assert (
        north.post(
            f"{NORTH}/members",
            json={
                "name": "Operador inicial",
                "email": "operador@example.org",
                "password": PASSWORD,
                "role_code": role["code"],
            },
        ).status_code
        == 201
    )
    target = next(
        row
        for row in north.get(f"{NORTH}/staff").json()["items"]
        if row["email"] == "operador@example.org"
    )
    assert (
        north.put(
            f"{NORTH}/roles/{role['code']}",
            json={
                "name": "Administrador adicional",
                "permissions": ["settings.manage"],
            },
        ).status_code
        == 409
    )
    assert (
        north.put(
            f"{NORTH}/staff/{target['id']}",
            json={
                "display_name": "Nuevo nombre",
                "role_code": role["code"],
                "active": True,
            },
        ).status_code
        == 200
    )
    assert south.get(f"{SOUTH}/staff/{target['id']}/sessions").status_code == 404
    with closing(TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})) as visitor:
        assert login(visitor, "operador@example.org").status_code == 200
        assert visitor.get(f"{NORTH}/records/customers").status_code == 200
        assert (
            visitor.post(f"{NORTH}/records/customers", json={"name": "Sin permiso"}).status_code
            == 403
        )
        assert visitor.get(f"{NORTH}/customers/export").status_code == 403
        assert visitor.get(f"{NORTH}/catalog").status_code == 403
        assert visitor.get(f"{NORTH}/settings").status_code == 403
        (authorized,) = north.get(f"{NORTH}/staff/{target['id']}/sessions").json()
        assert (
            north.post(
                f"{NORTH}/staff/{target['id']}/sessions/{authorized['id']}/revoke"
            ).status_code
            == 200
        )
        assert visitor.get("/api/auth/me").status_code == 401
    assert (
        north.put(
            f"{NORTH}/staff/{target['id']}",
            json={
                "display_name": "Inactivo",
                "role_code": role["code"],
                "active": False,
            },
        ).status_code
        == 200
    )
    for index in range(4):
        assert (
            member(platform, "norte-fase3", f"puesto{index}@example.org", "cashier").status_code
            == 201
        )
    assert (
        north.put(
            f"{NORTH}/staff/{target['id']}",
            json={
                "display_name": "Inactivo",
                "role_code": role["code"],
                "active": True,
            },
        ).status_code
        == 409
    )
    assert north.post(f"{NORTH}/staff/{target['id']}/recover").status_code == 202
    assert (
        north.get(f"{NORTH}/audit", params={"action": "restaurant.staff.revoke"}).json()["total"]
        == 1
    )


def test_invitation_reserves_releases_and_converts_seat(tenants, monkeypatch):
    app, platform, north, _ = tenants
    app.state.settings.smtp_mode = "mock"
    smtp = {
        "host": "smtp.example.org",
        "port": 587,
        "sender_email": "sender@example.org",
        "enabled": True,
        "security": "starttls",
    }
    assert platform.put("/api/platform/smtp", json=smtp).status_code == 200
    messages = []
    original = platform_admin.deliver

    def capture(settings, config, address, title, message):
        messages.append(message)
        return original(settings, config, address, title, message)

    monkeypatch.setattr(platform_admin, "deliver", capture)
    for index in range(3):
        assert (
            member(platform, "norte-fase3", f"puesto{index}@example.org", "cashier").status_code
            == 201
        )
    data = {"email": "pendiente@example.org", "name": "Personal pendiente", "role": "waiter"}
    assert (
        north.post(f"{NORTH}/staff-invitations", json={**data, "role": "admin"}).status_code == 409
    )
    assert north.post(f"{NORTH}/staff-invitations", json=data).json()["status"] == "simulated"
    assert north.post(f"{NORTH}/staff-invitations", json=data).status_code == 429
    assert north.get(f"{NORTH}/staff").json()["held"]["staff"] == 4
    assert member(platform, "norte-fase3", "otro@example.org", "waiter").status_code == 409
    expired = messages[-1].split("#token=")[1]
    assert (
        north.post(f"{NORTH}/staff-invitations/cancel", json={"email": data["email"]}).status_code
        == 200
    )
    assert north.get(f"{NORTH}/staff-invitations").json()[0]["state"] == "cancelled"
    assert north.get(f"{NORTH}/staff").json()["held"]["staff"] == 3
    assert north.post(f"{NORTH}/staff-invitations", json=data).status_code == 201
    token = messages[-1].split("#token=")[1]
    with closing(TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})) as invitee:
        assert (
            invitee.post(
                "/api/auth/invitations/accept", json={"token": expired, "password": PASSWORD}
            ).status_code
            == 400
        )
        result = invitee.post(
            "/api/auth/invitations/accept", json={"token": token, "password": PASSWORD}
        )
        assert result.status_code == 200, result.text
        assert login(invitee, data["email"]).status_code == 200
        assert invitee.get(f"{NORTH}/staff").status_code == 403
    staff = north.get(f"{NORTH}/staff").json()
    assert staff["usage"] == staff["held"] and staff["usage"]["staff"] == 4


def test_subscription_request_and_expired_entitlements(tenants):
    _, platform, north, south = tenants
    assert north.get(f"{NORTH}/subscription").json()["plan"]["code"] == "basic"
    pending = north.post(
        f"{NORTH}/subscription/requests", json={"plan_code": "pro", "notes": "Más cupos"}
    )
    assert pending.status_code == 201
    assert (
        north.post(f"{NORTH}/subscription/requests", json={"plan_code": "pro"}).status_code == 409
    )
    assert (
        north.post(f"{NORTH}/subscription/requests", json={"plan_code": "basic"}).status_code == 422
    )
    assert south.delete(f"{SOUTH}/subscription/requests/{pending.json()['id']}").status_code == 404
    assert any(
        item["kind"] == "plan_change_requested"
        for item in platform.get("/api/platform/notifications").json()
    )
    assert north.delete(f"{NORTH}/subscription/requests/{pending.json()['id']}").status_code == 204
    assert north.delete(f"{NORTH}/subscription/requests/{pending.json()['id']}").status_code == 409
    assert (
        north.post(f"{NORTH}/subscription/requests", json={"plan_code": "pro"}).status_code == 201
    )
    make_subscription(
        platform,
        "norte-fase3",
        "pro",
        pending=False,
        starts_on=(today() - timedelta(days=40)).isoformat(),
        ends_on=(today() - timedelta(days=8)).isoformat(),
    )
    status = north.get(f"{NORTH}/subscription").json()
    assert status["subscription"]["state"] == "expired"
    assert status["requests"][0]["status"] in {"approved", "cancelled"}
    assert any(item["status"] == "approved" for item in status["requests"])
    assert status["plan"]["code"] == "pro"
    assert north.get(f"{NORTH}/records/items").status_code == 403
    assert north.get(f"{NORTH}/overview").status_code == 200
