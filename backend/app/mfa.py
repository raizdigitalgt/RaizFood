import secrets

import pyotp
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import MfaCredential, now


def cipher(settings: Settings) -> Fernet:
    if settings.encryption_key is None:
        raise ValueError("Configura ENCRYPTION_KEY para administrar el segundo factor")
    return Fernet(settings.encryption_key.get_secret_value())


def verify_mfa(db: Session, settings: Settings, user_id: str, code: str | None):
    credential = db.get(MfaCredential, user_id)
    if not credential:
        raise HTTPException(403, "Solicita la activación de la autenticación de dos factores.")
    if not code:
        raise HTTPException(401, "Ingresa el código de autenticación.")
    seed = cipher(settings).decrypt(credential.encrypted_seed.encode()).decode()
    totp = pyotp.TOTP(seed)
    step = now() // totp.interval
    for candidate in (step + 1, step, step - 1):
        if candidate > credential.last_step and secrets.compare_digest(
            code, totp.generate_otp(candidate)
        ):
            credential.last_step = candidate
            return
    raise HTTPException(401, "Código de autenticación inválido o vencido.")
