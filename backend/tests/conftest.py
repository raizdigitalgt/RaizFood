import secrets
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.access import seed_plans
from app.auth import hasher
from app.config import Settings
from app.db import write_transaction
from app.main import create_app
from app.models import User

ORIGIN = "https://raizfood.test"
PASSWORD = "Pruebas de Raiz Food 2026"
ADMIN = "platform@example.org"


@pytest.fixture
def service(monkeypatch, tmp_path):
    path = tmp_path / "integration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FRONTEND_URL", ORIGIN)
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "400")
    settings = Settings()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    app = create_app(settings)
    engine = app.state.engine
    with Session(engine) as db, write_transaction(db):
        seed_plans(db, settings)
        db.add(
            User(
                name="Super Admin",
                email=ADMIN,
                platform_admin=True,
                password_hash=hasher.hash(PASSWORD),
            )
        )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield app, client


def login(client, email=ADMIN, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def restaurant(client, slug, plan="basic"):
    response = client.post(
        "/api/platform/restaurants",
        json={
            "name": f"Restaurante {slug}",
            "slug": slug,
            "plan_code": plan,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def member(client, slug, email, role="admin"):
    return client.post(
        f"/api/platform/restaurants/{slug}/members",
        json={
            "name": "Usuario de prueba",
            "email": email,
            "password": PASSWORD,
            "role_code": role,
        },
    )
