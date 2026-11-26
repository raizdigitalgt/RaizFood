import sqlite3
from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app import (
    auth,
    backups,
    commercial,
    commercial_choices,
    operations,
    platform_admin,
    platform_reporting,
)
from app.config import BACKEND, Settings
from app.db import database_engine


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    engine = database_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            with engine.connect() as connection:
                migrations = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
                applied = set(
                    connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars()
                )
                if applied != set(migrations.get_heads()):
                    raise RuntimeError("Ejecuta alembic upgrade head antes de iniciar Raíz Food")
            yield
        finally:
            engine.dispose()

    development = settings.app_env != "production"
    app = FastAPI(
        title="Raíz Food",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if development else None,
    )
    app.state.settings = settings
    app.state.engine = engine

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        if settings.maintenance_mode:
            return JSONResponse({"detail": "Servicio en mantenimiento"}, status_code=503)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if (
                request.headers.get("origin") != settings.frontend_url.rstrip("/")
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"detail": "Origen no autorizado"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        return JSONResponse(
            {
                "detail": [
                    {key: issue[key] for key in ("loc", "msg", "type")} for issue in error.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(OperationalError)
    async def sqlite_error(_request: Request, error: OperationalError):
        code = getattr(error.orig, "sqlite_errorcode", 0)
        if code & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return JSONResponse(
                {"detail": "Base de datos ocupada. Intenta nuevamente."},
                status_code=503,
                headers={"Retry-After": "1"},
            )
        raise error

    @app.get("/api/health", tags=["Servicio"])
    def health():
        with engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        return {"status": "ok", "database": "sqlite", "journal_mode": mode}

    app.include_router(auth.router, prefix="/api")
    app.include_router(operations.platform, prefix="/api")
    app.include_router(operations.restaurant, prefix="/api")
    app.include_router(commercial.router, prefix="/api")
    app.include_router(commercial_choices.router, prefix="/api")
    app.include_router(platform_admin.router, prefix="/api")
    app.include_router(platform_admin.public, prefix="/api")
    app.include_router(platform_reporting.router, prefix="/api")
    app.include_router(backups.router, prefix="/api")
    return app
