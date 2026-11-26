import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import monotonic

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.access import audit
from app.auth import DB
from app.commercial import notify, options, save_option, values
from app.commercial_models import BackupRecord
from app.commercial_schemas import BackupSettings
from app.config import BACKEND, Settings
from app.db import write_transaction
from app.models import AuditLog, now, uuid
from app.platform_access import platform_user

router = APIRouter(prefix="/platform", tags=["Respaldos"])
DEFAULT_POLICY = BackupSettings().model_dump()


def database_path(settings: Settings):
    return (BACKEND / Path(make_url(settings.database_url).database)).resolve()


def backup_root(settings: Settings):
    path = settings.backup_directory or database_path(settings).parent / "backups"
    root = (BACKEND / path).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def integrity(path: Path, *, immutable=False):
    query = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    with closing(sqlite3.connect(path.as_uri() + query, uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Falló la comprobación de integridad")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("El respaldo contiene relaciones inválidas")
        return db.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def checksum(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exclusive_file(path: Path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)


def copy_database(source: Path, target: Path, *, standalone=True):
    deadline = monotonic() + 30

    def progress(_state, _remaining, _total):
        if monotonic() > deadline:
            raise TimeoutError("No se pudo terminar la copia SQLite")

    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original:
        with closing(sqlite3.connect(target, timeout=5)) as destination:
            original.backup(destination, pages=128, sleep=0.05, progress=progress)
            if standalone:
                destination.execute("PRAGMA journal_mode=DELETE")


def generate(settings: Settings):
    key = uuid()
    root = backup_root(settings)
    output = root / f"raizfood-{key}.db"
    staged = output.with_suffix(".partial")
    manifest = output.with_suffix(".json")
    exclusive_file(staged)
    try:
        copy_database(database_path(settings), staged)
        revision = integrity(staged, immutable=True)
        digest = checksum(staged)
        size = staged.stat().st_size
        exclusive_file(manifest)
        manifest.write_text(
            json.dumps(
                {
                    "file": output.name,
                    "sha256": digest,
                    "bytes": size,
                    "revision": revision,
                    "created_at": now(),
                    "integrity": "ok",
                    "assets": "embedded-in-sqlite",
                }
            ),
            encoding="utf-8",
        )
        staged.rename(output)
        return BackupRecord(
            id=key,
            filename=output.name,
            size=size,
            checksum=digest,
            revision=revision,
            state="verified",
        )
    except (OSError, ValueError, sqlite3.Error):
        staged.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        raise


def backup_files(settings: Settings, name: str):
    if not re.fullmatch(r"raizfood-[a-f0-9-]{36}\.db", name):
        raise ValueError("Nombre de respaldo inválido")
    path = backup_root(settings) / name
    if path.is_symlink() or path.with_suffix(".json").is_symlink():
        raise ValueError("Ruta de respaldo inválida")
    return path, path.with_suffix(".json")


def verify_file(path: Path, manifest: Path):
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        meta["file"] != path.name
        or meta["bytes"] != path.stat().st_size
        or meta["sha256"] != checksum(path)
        or meta["revision"] != integrity(path, immutable=True)
    ):
        raise ValueError("El respaldo y su manifiesto no coinciden")
    return meta


def restore(settings: Settings, source: Path, target: Path, authorized: bool):
    if not authorized:
        raise ValueError("La restauración requiere confirmación explícita")
    verify_file(source, source.with_suffix(".json"))
    active = target.resolve() == database_path(settings)
    if target.resolve() == source.resolve():
        raise ValueError("El origen y el destino deben ser diferentes")
    if active:
        if not settings.maintenance_mode:
            raise ValueError("La restauración activa requiere MAINTENANCE_MODE=true")
        snapshot = generate(settings)
        previous, _ = backup_files(settings, snapshot.filename)
        try:
            copy_database(source, target, standalone=False)
            integrity(target)
        except (OSError, ValueError, sqlite3.Error):
            copy_database(previous, target, standalone=False)
            raise
        return snapshot
    if target.exists():
        raise ValueError("El destino independiente debe ser un archivo nuevo")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    exclusive_file(target)
    try:
        copy_database(source, target)
        integrity(target, immutable=True)
    except (OSError, ValueError, sqlite3.Error):
        target.unlink(missing_ok=True)
        raise
    return None


def present(backup):
    return values(backup, ("id", "filename", "size", "revision", "state", "created_at"))


@router.get("/backups")
def backup_list(request: Request, db: DB):
    platform_user(request, db, "backups")
    rows = db.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(200))
    return {
        "items": [present(row) for row in rows],
        "settings": options(db, "backups", DEFAULT_POLICY),
    }


@router.put("/backups/settings")
def backup_policy(data: BackupSettings, request: Request, db: DB):
    with write_transaction(db):
        actor = platform_user(request, db, "backups")
        save_option(db, "backups", data.model_dump())
        audit(db, actor, "backup.settings", "backups")
    return data


@router.post("/backups", status_code=201)
def create_backup(request: Request, db: DB):
    actor_id = platform_user(request, db, "backups").id
    db.rollback()
    settings = request.app.state.settings
    try:
        record = generate(settings)
    except (OSError, ValueError, sqlite3.Error) as error:
        with write_transaction(db):
            db.add(
                AuditLog(
                    user_id=actor_id, action="backup.generate", subject="backups", result="failed"
                )
            )
            notify(db, f"backup-failed:{uuid()}", "backup_error", "No se pudo crear un respaldo")
        raise HTTPException(503, "No se pudo crear un respaldo verificable") from error
    with write_transaction(db):
        db.add(record)
        db.add(AuditLog(user_id=actor_id, action="backup.generate", subject=record.id))
    return present(record)


def selected_backup(key, request, db, permission):
    actor_id = platform_user(request, db, permission).id
    record = db.get(BackupRecord, key)
    if not record or record.state == "expired":
        raise HTTPException(404, "Respaldo no disponible")
    return actor_id, backup_files(request.app.state.settings, record.filename)


@router.post("/backups/{key}/verify")
def verify_backup(key: str, request: Request, db: DB):
    actor, paths = selected_backup(key, request, db, "backups")
    expected = db.get(BackupRecord, key).checksum
    db.rollback()
    try:
        valid = verify_file(*paths)["sha256"] == expected
    except (OSError, ValueError, KeyError, sqlite3.Error):
        valid = False
    with write_transaction(db):
        record = db.get(BackupRecord, key)
        if record.state == "expired":
            raise HTTPException(404, "Respaldo no disponible")
        record.state = "verified" if valid else "invalid"
        db.add(
            AuditLog(
                user_id=actor,
                action="backup.verify",
                subject=key,
                result="ok" if valid else "failed",
            )
        )
    return {"valid": valid}


@router.get("/backups/{key}/download/{format}")
def download_backup(key: str, format: str, request: Request, db: DB):
    actor, (path, manifest) = selected_backup(key, request, db, "backups.download")
    expected = db.get(BackupRecord, key).checksum
    db.rollback()
    if format not in {"db", "manifest"}:
        raise HTTPException(404, "Formato no disponible")
    try:
        valid = verify_file(path, manifest)["sha256"] == expected
    except (OSError, ValueError, KeyError, sqlite3.Error):
        valid = False
    if not valid:
        raise HTTPException(409, "El respaldo no pasó la verificación")
    with write_transaction(db):
        db.add(AuditLog(user_id=actor, action="backup.download", subject=key))
    file = path if format == "db" else manifest
    return FileResponse(file, filename=file.name, media_type="application/octet-stream")
