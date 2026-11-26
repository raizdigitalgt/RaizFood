import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.auth import hasher
from app.config import Settings
from app.models import Membership, Tenant, User
from tests.conftest import PASSWORD


def test_development_seed_is_idempotent_and_blocked_in_test(service, monkeypatch):
    app, client = service
    settings = app.state.settings
    with pytest.raises(SystemExit, match="demostración"):
        cli.seed_demo(settings)
    encoded = hasher.hash(PASSWORD)
    monkeypatch.setattr(cli, "read_password", lambda: encoded)
    development = Settings(app_env="development")
    cli.seed_demo(development)
    cli.seed_demo(development)
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Tenant)) == 2
        assert db.scalar(select(func.count()).select_from(Membership)) == 9
        assert db.scalar(select(func.count()).select_from(User)) == 10
    identity = client.post(
        "/api/auth/login",
        json={
            "email": "admin1@taqueria-central.example.org",
            "password": PASSWORD,
        },
    )
    assert identity.status_code == 200
    assert identity.json()["tenant"]["slug"] == "taqueria-central"
