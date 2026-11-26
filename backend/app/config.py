from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_ignore_empty=True)

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./.data/raizfood.db"
    sqlite_busy_timeout_ms: int = Field(10000, ge=1, le=60000)
    frontend_url: str = "http://localhost:3000"
    jwt_secret_key: SecretStr
    encryption_key: SecretStr | None = None
    smtp_allowed_hosts: str = ""
    smtp_mode: Literal["live", "mock"] = "live"
    backup_directory: Path | None = None
    maintenance_mode: bool = False
    access_token_expire_minutes: int = Field(15, ge=1, le=30)
    refresh_token_expire_days: int = Field(7, ge=1, le=30)
    basic_monthly_cents: int = Field(15000, ge=0)
    pro_monthly_cents: int = Field(27500, ge=0)

    @model_validator(mode="after")
    def validate_security(self):
        if len(self.jwt_secret_key.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 bytes")
        if self.app_env == "production" and not self.frontend_url.startswith("https://"):
            raise ValueError("FRONTEND_URL requiere HTTPS en producción")
        if self.app_env == "production" and self.smtp_mode == "mock":
            raise ValueError("SMTP_MODE=mock se reserva para desarrollo y pruebas")
        if self.app_env == "production" and self.encryption_key is None:
            raise ValueError("ENCRYPTION_KEY es obligatoria en producción")
        if self.encryption_key is not None:
            from cryptography.fernet import Fernet

            Fernet(self.encryption_key.get_secret_value())
        return self
