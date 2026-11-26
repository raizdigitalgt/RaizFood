from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.commercial_models import PlatformSetting
from app.models import User

PERMISSIONS = {
    "dashboard",
    "restaurants",
    "plans",
    "subscriptions",
    "payments",
    "audit",
    "users",
    "settings",
    "smtp",
    "branding",
    "backups",
    "backups.download",
    "notifications",
    "support",
    "fel",
    "reports",
}
ROLE_GRANTS = {
    "super": PERMISSIONS,
    "admin": PERMISSIONS - {"users", "backups.download", "smtp"},
    "commercial": {
        "dashboard",
        "restaurants",
        "plans",
        "subscriptions",
        "payments",
        "notifications",
        "reports",
    },
    "support": {"dashboard", "notifications", "support"},
    "auditor": {"dashboard", "audit", "reports"},
}


def platform_grants(db: Session, user: User) -> set[str]:
    if not user.platform_admin:
        return set()
    role = user.platform_role or "super"
    override = db.get(PlatformSetting, f"role:{role}") if role != "super" else None
    return set(override.value["permissions"]) if override else ROLE_GRANTS.get(role, set())


def platform_user(request: Request, db: Session, permission: str = "dashboard"):
    from app.auth import credentials

    _, user = credentials(request, db)
    if permission not in platform_grants(db, user):
        raise HTTPException(403, "Permiso de plataforma insuficiente")
    return user
