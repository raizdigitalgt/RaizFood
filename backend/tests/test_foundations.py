import re
from concurrent.futures import ThreadPoolExecutor

import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import ACCESS, REFRESH
from app.cli import enroll_mfa, reset_link
from app.config import Settings
from app.models import Tenant, User
from tests.conftest import ORIGIN, PASSWORD, login, member, restaurant


def test_sqlite_configuration(service):
    app, client = service
    assert client.get("/api/health").json()["journal_mode"] == "wal"
    with app.state.engine.connect() as connection:
        for pragma, expected in {"foreign_keys": 1, "synchronous": 2, "busy_timeout": 400}.items():
            assert connection.exec_driver_sql(f"PRAGMA {pragma}").scalar() == expected


def test_login_csrf_and_rotation(service):
    _, client = service
    assert client.get("/api/platform/dashboard").status_code == 401
    assert login(client, password="incorrecta").status_code == 401
    assert (
        client.post("/api/auth/login", headers={"Origin": "https://otro.test"}).status_code == 403
    )
    response = login(client)
    assert response.status_code == 200, response.text
    assert all("httponly" in value.lower() for value in response.headers.get_list("set-cookie"))
    assert client.get("/api/platform/dashboard").json()["restaurants"] == 0
    original = client.cookies.get(REFRESH)
    assert client.post("/api/auth/refresh").status_code == 200
    assert client.cookies.get(REFRESH) != original

    with TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as second:
        second.cookies.set(REFRESH, original, path="/api/auth")
        assert second.post("/api/auth/refresh").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_access(service):
    _, client = service
    assert login(client).status_code == 200
    access = client.cookies.get(ACCESS)
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(ACCESS, access)
    assert client.get("/api/auth/me").status_code == 401


def test_platform_mfa_in_production(service, monkeypatch, capsys):
    app, client = service
    assert login(client).status_code == 200
    previous_refresh = client.cookies.get(REFRESH)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    settings = Settings()
    app.state.settings = settings
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 403
    client.cookies.set(REFRESH, previous_refresh, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    enroll_mfa(settings, "platform@example.org")
    seed = capsys.readouterr().out.splitlines()[-1]
    challenge = login(client)
    assert challenge.status_code == 401
    assert challenge.json()["detail"] == "Ingresa el código de autenticación."
    code = pyotp.TOTP(seed).now()
    body = {"email": "platform@example.org", "password": PASSWORD, "otp": code}
    verified = client.post("/api/auth/login", json=body)
    assert verified.status_code == 200
    assert all("secure" in value.lower() for value in verified.headers.get_list("set-cookie"))
    assert client.get("/api/platform/dashboard").status_code == 200
    assert client.post("/api/auth/login", json=body).status_code == 401


def test_password_reset_single_use(service, capsys):
    app, client = service
    assert login(client).status_code == 200
    reset_link(app.state.settings, "platform@example.org")
    token = re.search(r"#token=(\S+)", capsys.readouterr().out).group(1)
    replacement = "Una contraseña recuperada"
    body = {"token": token, "password": replacement}
    assert client.post("/api/auth/reset", json=body).status_code == 200
    assert client.post("/api/auth/reset", json=body).status_code == 400
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=replacement).status_code == 200


def test_isolation_roles_and_tenant_switch(service):
    _, platform = service
    assert login(platform).status_code == 200
    restaurant(platform, "central")
    restaurant(platform, "norte", "pro")
    assert member(platform, "central", "admin@example.org").status_code == 201
    assert member(platform, "central", "caja@example.org", "cashier").status_code == 201
    assert member(platform, "norte", "norte@example.org").status_code == 201
    assert platform.get("/api/restaurants/central/dashboard").status_code == 404
    with TestClient(platform.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        assert login(client, "admin@example.org").json()["tenant"]["slug"] == "central"
        assert client.get("/api/platform/dashboard").status_code == 403
        assert client.get("/api/restaurants/norte/dashboard").status_code == 404
        assert client.get("/api/restaurants/norte/members").status_code == 404
        data = client.get("/api/restaurants/central/members").json()
        assert {row["email"] for row in data["items"]} == {"admin@example.org", "caja@example.org"}
        assert "fel.issue" not in client.get("/api/auth/me").json()["permissions"]
        assert client.post("/api/auth/tenant", json={"slug": "norte"}).status_code == 404
        assert login(client, "caja@example.org").status_code == 200
        assert client.get("/api/restaurants/central/members").status_code == 403
        assert (
            client.post(
                "/api/restaurants/central/members",
                json={
                    "email": "otro@example.org",
                    "name": "Operación",
                    "password": PASSWORD,
                    "role_code": "admin",
                },
            ).status_code
            == 403
        )
        assert (
            platform.post(
                "/api/platform/restaurants/norte/members",
                json={
                    "email": "admin@example.org",
                    "role_code": "admin",
                },
            ).status_code
            == 201
        )
        identity = login(client, "admin@example.org").json()
        assert identity["tenant"] is None
        assert {row["slug"] for row in identity["restaurants"]} == {"central", "norte"}
        assert client.post("/api/auth/tenant", json={"slug": "norte"}).status_code == 200
        assert "fel.issue" in client.get("/api/auth/me").json()["permissions"]
        assert client.get("/api/restaurants/central/dashboard").status_code == 404
        assert client.get("/api/restaurants/norte/dashboard").status_code == 200


def test_plan_limits_and_rollback(service):
    app, client = service
    assert login(client).status_code == 200
    for code, admins, staff, price in (("basic", 1, 4, 15000), ("pro", 2, 8, 27500)):
        plan = restaurant(client, code, code)["plan"]
        assert plan["monthly_cents"] == price
        for role, maximum in (("admin", admins), ("cashier", staff)):
            for index in range(maximum):
                assert (
                    member(client, code, f"{code}-{role}-{index}@example.org", role).status_code
                    == 201
                )
            extra = f"{code}-{role}-extra@example.org"
            assert member(client, code, extra, role).status_code == 409
            with Session(app.state.engine) as db:
                assert db.scalar(select(User.id).where(User.email == extra)) is None
    assert client.get("/api/platform/restaurants", params={"q": "basic"}).json()["total"] == 1
    assert client.get("/api/platform/restaurants", params={"q": "%"}).json()["total"] == 0


def test_concurrent_last_admin_and_lock(service):
    app, client = service
    assert login(client).status_code == 200
    restaurant(client, "concurrente")
    cookie = client.cookies.get(ACCESS)

    def add(number):
        with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as caller:
            caller.cookies.set(ACCESS, cookie)
            return member(caller, "concurrente", f"admin{number}@example.org").status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(add, (1, 2))) == [201, 409]

    with app.state.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        reply = client.post(
            "/api/platform/restaurants",
            json={
                "name": "Bajo bloqueo",
                "slug": "bloqueado",
                "plan_code": "basic",
            },
        )
        assert reply.status_code == 503
        assert reply.headers["Retry-After"] == "1"
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Tenant)) == 1
