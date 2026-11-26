from base64 import b64encode
from datetime import timedelta
from io import BytesIO

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import platform_admin
from app.backups import backup_files, integrity, restore
from app.commercial_models import MailJob, PlatformSetting
from app.config import Settings
from app.entitlements import today
from app.maintenance import scheduled
from tests.conftest import ORIGIN, login, restaurant
from tests.test_commercial import P, make_subscription


def test_smtp_invitation_recovery_and_branding(service, monkeypatch):
    app, client = service
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SMTP_MODE", "mock")
    app.state.settings = Settings()
    assert login(client).status_code == 200
    restaurant(client, "correo")
    smtp = {
        "host": "smtp.example.org",
        "port": 587,
        "enabled": True,
        "security": "starttls",
        "sender_email": "sender@example.org",
        "username": "pruebas",
        "password": "clave simulada",
    }
    response = client.put(f"{P}/smtp", json=smtp)
    assert response.status_code == 200, response.text
    assert response.json()["has_password"] and "password" not in response.json()
    with Session(app.state.engine) as db:
        stored = db.get(PlatformSetting, "smtp").value["encrypted_password"]
        assert stored != smtp["password"]
        assert (
            Fernet(app.state.settings.encryption_key.get_secret_value()).decrypt(stored)
            == b"clave simulada"
        )
    assert (
        client.post(f"{P}/smtp/test", json={"email": "destino@example.org"}).json()["status"]
        == "simulated"
    )
    assert client.post(f"{P}/smtp/test", json={"email": "destino@example.org"}).status_code == 429
    original = platform_admin.deliver
    inbox = []

    def capture(settings, config, address, subject, body):
        inbox.append((address, subject, body))
        return original(settings, config, address, subject, body)

    monkeypatch.setattr(platform_admin, "deliver", capture)
    invitation = client.post(
        f"{P}/restaurants/correo/invitations",
        json={
            "name": "Administrador invitado",
            "email": "invited@example.org",
            "role": "admin",
        },
    )
    assert invitation.status_code == 201, invitation.text
    invite_token = inbox[-1][2].split("#token=")[1]
    password = "Una contraseña ficticia"
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as guest:
        payload = {"token": invite_token, "password": password}
        assert guest.post("/api/auth/invitations/accept", json=payload).status_code == 200
        assert guest.post("/api/auth/invitations/accept", json=payload).status_code == 400
        current = login(guest, "invited@example.org", password).json()
        assert current["tenant"]["slug"] == "correo"
        assert (
            guest.post("/api/auth/recover", json={"email": "invited@example.org"}).status_code
            == 202
        )
        reset_token = inbox[-1][2].split("#token=")[1]
        assert (
            guest.post(
                "/api/auth/reset", json={"token": reset_token, "password": "Segunda contraseña"}
            ).status_code
            == 200
        )
        assert guest.get("/api/auth/me").status_code == 401
        assert login(guest, "invited@example.org", "Segunda contraseña").status_code == 200
    assert scheduled(app.state.settings) == 0
    with Session(app.state.engine) as db:
        jobs = db.scalars(select(MailJob)).all()
        assert len(jobs) == 1 and jobs[0].state == "simulated"
    assert all(
        "token" not in row["detail"] and "clave simulada" not in row["detail"]
        for row in client.get(f"{P}/audit").json()
    )
    name = {"name": "Raíz Food Comercial", "contact": "Soporte de prueba", "primary": "#f06d20"}
    assert client.put(f"{P}/branding", json=name).json()["name"] == name["name"]
    image = BytesIO()
    Image.new("RGB", (10, 12), "orange").save(image, format="PNG")
    valid = {"content": b64encode(image.getvalue()).decode()}
    assert (
        client.put(f"{P}/branding/assets/login-logo", json={"content": "aGVsbG8="}).status_code
        == 422
    )
    assert client.put(f"{P}/branding/assets/login-logo", json=valid).status_code == 200
    assert client.get("/api/branding").json()["assets"] == ["login-logo"]
    assert client.get("/api/branding/assets/login-logo").content.startswith(b"\x89PNG")
    assert client.delete(f"{P}/branding/assets/login-logo").status_code == 200
    assert client.get("/api/branding/assets/login-logo").status_code == 404


def test_verified_backup_download_and_independent_restore(service, monkeypatch, tmp_path):
    app, client = service
    monkeypatch.setenv("BACKUP_DIRECTORY", str(tmp_path / "protected"))
    settings = Settings()
    app.state.settings = settings
    assert login(client).status_code == 200
    restaurant(client, "respaldo")
    created = client.post(f"{P}/backups")
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["revision"] == "0005" and row["state"] == "verified"
    path, manifest = backup_files(settings, row["filename"])
    target = tmp_path / "restore" / "independent.db"
    with pytest.raises(ValueError, match="confirmación"):
        restore(settings, path, target, False)
    restore(settings, path, target, True)
    assert integrity(target, immutable=True) == "0005"
    assert client.post(f"{P}/backups/{row['id']}/verify").json()["valid"] is True
    assert client.get(f"{P}/backups/{row['id']}/download/db").content.startswith(b"SQLite format 3")
    assert b"sha256" in client.get(f"{P}/backups/{row['id']}/download/manifest").content
    assert (
        client.put(
            f"{P}/backups/settings",
            json={
                "automatic": True,
                "interval_hours": 6,
                "retention_days": 90,
            },
        ).status_code
        == 200
    )
    assert client.get(f"{P}/backups").json()["settings"]["retention_days"] == 90
    assert manifest.is_file()
    assert client.get(f"{P}/commercial-summary").json()["backup"]["id"] == row["id"]


def test_schedule_notifications_support_settings_and_fel(service):
    app, client = service
    assert login(client).status_code == 200
    restaurant(client, "soporte", "pro")
    sub = make_subscription(
        client, "soporte", "pro", pending=False, ends_on=(today() + timedelta(days=2)).isoformat()
    )
    assert sub["state"] == "active"
    assert scheduled(app.state.settings) == 1
    assert scheduled(app.state.settings) == 1
    result = client.post(
        f"{P}/support",
        json={
            "restaurant": "soporte",
            "subject": "Consulta de acceso",
            "description": "Detalle de la solicitud",
            "priority": "high",
        },
    )
    assert result.status_code == 201, result.text
    ticket = result.json()
    assert client.get(f"{P}/support").json()[0]["subject"] == ticket["subject"]
    assert client.get(f"{P}/restaurant-options").json()[0]["slug"] == "soporte"
    assignee = client.get(f"{P}/support-assignees").json()[0]
    change = client.put(
        f"{P}/support/{ticket['id']}",
        json={
            "state": "in_progress",
            "assignee_id": assignee["id"],
            "message": "En seguimiento",
        },
    )
    assert change.status_code == 200
    assert len(change.json()["history"]) == 2
    notices = client.get(f"{P}/notifications").json()
    assert {row["kind"] for row in notices} == {"subscription_expiring", "support_request"}
    assert client.post(f"{P}/notifications/{notices[0]['id']}/read").status_code == 200
    assert client.get(f"{P}/notifications").json()[0]["read"]
    assert client.put(
        f"{P}/settings",
        json={
            "payment_methods": ["Efectivo", "Otro"],
            "platform_name": "Raíz Food",
        },
    ).json()["payment_methods"] == ["Efectivo", "Otro"]
    assert client.get(f"{P}/payment-methods").json()[-1] == "Otro"
    assert client.get(f"{P}/settings").json()["platform_name"] == "Raíz Food"
    assert client.get(f"{P}/security").json()["active_sessions"] >= 1
    assert client.get(f"{P}/fel").json()["restaurants"][0]["slug"] == "soporte"


def test_scheduled_retention_invalid_copy_and_download_scope(service, monkeypatch, tmp_path):
    app, client = service
    root = tmp_path / "backup-policy"
    monkeypatch.setenv("BACKUP_DIRECTORY", str(root))
    settings = Settings()
    app.state.settings = settings
    assert login(client).status_code == 200
    assert (
        client.put(
            f"{P}/backups/settings",
            json={
                "automatic": True,
                "interval_hours": 1,
                "retention_days": 1,
            },
        ).status_code
        == 200
    )
    assert scheduled(settings) == 0
    (old,) = client.get(f"{P}/backups").json()["items"]
    with Session(app.state.engine) as db:
        from app.commercial_models import BackupRecord

        record = db.get(BackupRecord, old["id"])
        record.created_at -= 2 * 86400
        db.commit()
    assert scheduled(settings) == 0
    items = client.get(f"{P}/backups").json()["items"]
    current = next(item for item in items if item["state"] == "verified")
    assert any(item["state"] == "expired" for item in items)
    assert not (root / old["filename"]).exists()
    assert client.get(f"{P}/backups/{old['id']}/download/db").status_code == 404
    password = "Contraseña ficticia de respaldo"
    assert (
        client.post(
            f"{P}/users",
            json={
                "name": "Administrador delegado",
                "role": "admin",
                "email": "delegado@example.org",
                "password": password,
            },
        ).status_code
        == 201
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as delegate:
        assert login(delegate, "delegado@example.org", password).status_code == 200
        assert delegate.get(f"{P}/backups").status_code == 200
        assert delegate.get(f"{P}/backups/{current['id']}/download/db").status_code == 403
    _, manifest = backup_files(settings, current["filename"])
    manifest.write_text("{}", encoding="utf-8")
    assert client.post(f"{P}/backups/{current['id']}/verify").json()["valid"] is False
    assert client.get(f"{P}/backups/{current['id']}/download/db").status_code == 409
