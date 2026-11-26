from app.access import seed_plans
from app.auth import hasher
from app.cli import connect
from app.config import Settings
from app.db import write_transaction
from app.models import User

settings = Settings()
if settings.app_env != "test" or not settings.database_url.startswith("sqlite:///./.data/e2e/"):
    raise SystemExit("La siembra E2E requiere una base de pruebas dedicada.")
encoded = hasher.hash("Cuenta ficticia de Playwright")
with connect(settings) as db, write_transaction(db):
    seed_plans(db, settings)
    db.add(
        User(
            name="Equipo Raíz",
            email="platform@example.org",
            password_hash=encoded,
            platform_admin=True,
        )
    )
