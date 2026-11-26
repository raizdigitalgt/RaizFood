import argparse
import getpass
import secrets
from contextlib import contextmanager

import pyotp
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.access import ROLE_NAMES, add_member, audit, create_restaurant, seed_plans
from app.auth import digest, hasher
from app.config import Settings
from app.db import database_engine, write_transaction
from app.mfa import cipher
from app.models import MfaCredential, PasswordReset, Plan, Role, Tenant, User, now

EMAIL = TypeAdapter(EmailStr)
DEMO = (
    (
        "taqueria-central",
        "Taquería Central",
        "basic",
        ("admin", "cashier", "waiter", "cook", "inventory"),
    ),
    ("burger-house", "Burger House", "pro", ("admin", "admin", "cashier", "cook")),
)


def read_password():
    value = getpass.getpass("Contraseña (12–128 caracteres): ")
    if not 12 <= len(value) <= 128:
        raise SystemExit("La contraseña debe tener entre 12 y 128 caracteres")
    if value != getpass.getpass("Confirma la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    return hasher.hash(value)


def email_address(value: str):
    try:
        return EMAIL.validate_python(value).lower()
    except ValidationError as error:
        raise SystemExit("Correo inválido") from error


@contextmanager
def connect(settings):
    engine = database_engine(settings)
    try:
        with Session(engine, expire_on_commit=False) as db:
            yield db
    finally:
        engine.dispose()


def bootstrap(settings, email, name):
    email = email_address(email)
    name = name.strip()
    if not 2 <= len(name) <= 100:
        raise SystemExit("El nombre debe tener entre 2 y 100 caracteres")
    encoded = read_password()
    with connect(settings) as db, write_transaction(db):
        if db.scalar(select(User.id).where(User.platform_admin.is_(True)).limit(1)):
            raise SystemExit("Ya existe un superadministrador")
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("El correo ya existe")
        seed_plans(db, settings)
        user = User(name=name, email=email, password_hash=encoded, platform_admin=True)
        db.add(user)
        db.flush()
        audit(db, user, "platform.bootstrap", user.id)


def seed_demo(settings):
    if settings.app_env != "development":
        raise SystemExit("Los datos de demostración requieren APP_ENV=development")
    from app.restaurant_demo import seed_restaurant

    encoded = read_password()
    with connect(settings) as db, write_transaction(db):
        seed_plans(db, settings)
        for slug, name, code, roles in DEMO:
            present = db.scalar(select(Tenant).where(Tenant.slug == slug))
            if present:
                if present.name == f"{name} · Demo":
                    seed_restaurant(db, present, code)
                continue
            plan = db.scalar(select(Plan).where(Plan.code == code))
            tenant = create_restaurant(db, slug, f"{name} · Demo", plan)
            for number, code in enumerate(roles, start=1):
                role = db.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.code == code))
                user = User(
                    name=f"{ROLE_NAMES[code]} · Demo",
                    email=f"{code}{number}@{slug}.example.org",
                    password_hash=encoded,
                )
                db.add(user)
                db.flush()
                add_member(db, tenant, user, role)
                db.flush()
            seed_restaurant(db, tenant, code)
    print("Demostración inicializada. Las cuentas existentes conservan su contraseña.")


def reset_link(settings, email):
    email = email_address(email)
    token = secrets.token_urlsafe(32)
    with connect(settings) as db, write_transaction(db):
        user = db.scalar(select(User).where(User.email == email, User.active.is_(True)))
        if not user:
            raise SystemExit("Cuenta activa no encontrada")
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.add(PasswordReset(digest=digest(token), user_id=user.id, expires_at=now() + 900))
    print(f"{settings.frontend_url.rstrip('/')}/reset-password#token={token}")


def enroll_mfa(settings, email):
    email = email_address(email)
    encryptor = cipher(settings)
    seed = pyotp.random_base32()
    with connect(settings) as db, write_transaction(db):
        user = db.scalar(
            select(User).where(
                User.email == email, User.active.is_(True), User.platform_admin.is_(True)
            )
        )
        if not user or db.get(MfaCredential, user.id):
            raise SystemExit("Se requiere una cuenta de plataforma activa sin MFA")
        db.add(
            MfaCredential(user_id=user.id, encrypted_seed=encryptor.encrypt(seed.encode()).decode())
        )
        audit(db, user, "platform.mfa_enroll", user.id)
    print("Agrega esta clave a tu autenticador TOTP y guárdala en un lugar seguro.")
    print(seed)


def main():
    parser = argparse.ArgumentParser(prog="raizfood")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    commands.add_parser("seed-plans")
    commands.add_parser("seed-demo")
    reset = commands.add_parser("reset-link")
    reset.add_argument("--email", required=True)
    mfa = commands.add_parser("enroll-mfa")
    mfa.add_argument("--email", required=True)
    args = parser.parse_args()
    settings = Settings()
    match args.command:
        case "create-admin":
            bootstrap(settings, args.email, args.name)
            print("Superadministrador creado.")
        case "seed-plans":
            with connect(settings) as db, write_transaction(db):
                seed_plans(db, settings)
        case "seed-demo":
            seed_demo(settings)
        case "reset-link":
            reset_link(settings, args.email)
        case "enroll-mfa":
            enroll_mfa(settings, args.email)


if __name__ == "__main__":
    main()
