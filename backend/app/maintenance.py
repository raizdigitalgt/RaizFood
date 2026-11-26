import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import select

from app.backups import DEFAULT_POLICY, backup_files, generate, restore
from app.cli import connect
from app.commercial import notify, options
from app.commercial_models import BackupRecord
from app.config import Settings
from app.db import write_transaction
from app.mailer_queue import dispatch
from app.models import AuditLog, User, now, uuid
from app.platform_reporting import expiry_notifications


def scheduled(settings):
    with connect(settings) as db, write_transaction(db):
        count = expiry_notifications(db)
        policy = options(db, "backups", DEFAULT_POLICY)
        recent = db.scalar(
            select(BackupRecord)
            .where(BackupRecord.state == "verified")
            .order_by(BackupRecord.created_at.desc())
            .limit(1)
        )
        create = policy["automatic"] and (
            not recent or now() - recent.created_at >= policy["interval_hours"] * 3600
        )
        actor_id = maintenance_actor(db)
    if create:
        try:
            record = generate(settings)
        except (OSError, ValueError, sqlite3.Error):
            with connect(settings) as db, write_transaction(db):
                notify(
                    db, f"backup-failed:{uuid()}", "backup_error", "Falló el respaldo programado"
                )
                if actor_id:
                    db.add(
                        AuditLog(
                            user_id=actor_id,
                            action="backup.scheduled",
                            subject="backups",
                            result="failed",
                        )
                    )
            raise
        with connect(settings) as db, write_transaction(db):
            db.add(record)
            if actor_id:
                db.add(AuditLog(user_id=actor_id, action="backup.scheduled", subject=record.id))
    if policy["automatic"]:
        expire(settings, policy["retention_days"], actor_id)
    dispatch(settings, actor_id)
    return count


def maintenance_actor(db):
    return db.scalar(
        select(User.id)
        .where(
            User.platform_admin.is_(True),
            User.active.is_(True),
            (User.platform_role == "super") | User.platform_role.is_(None),
        )
        .order_by(User.created_at)
        .limit(1)
    )


def expire(settings, retention_days, actor_id):
    with connect(settings) as db, write_transaction(db):
        keep = db.scalar(
            select(BackupRecord.id)
            .where(BackupRecord.state == "verified")
            .order_by(BackupRecord.created_at.desc())
            .limit(1)
        )
        if not keep:
            return
        rows = db.scalars(
            select(BackupRecord).where(
                BackupRecord.state != "expired",
                BackupRecord.id != keep,
                BackupRecord.created_at < now() - retention_days * 86400,
            )
        ).all()
        files = [(row.id, row.filename) for row in rows]
        for row in rows:
            row.state = "expired"
            if actor_id:
                db.add(AuditLog(user_id=actor_id, action="backup.retention", subject=row.id))
    for _, filename in files:
        for path in backup_files(settings, filename):
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tick")
    recovery = commands.add_parser("restore")
    recovery.add_argument("--source", type=Path, required=True)
    recovery.add_argument("--target", type=Path, required=True)
    recovery.add_argument("--confirm", choices=["RESTAURAR"], required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "tick":
        print(f"Suscripciones revisadas: {scheduled(settings)}")
    else:
        try:
            snapshot = restore(
                settings, args.source.resolve(), args.target.resolve(), args.confirm == "RESTAURAR"
            )
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            raise SystemExit(str(error)) from error
        with connect(settings) as db, write_transaction(db):
            actor = maintenance_actor(db)
            if snapshot:
                db.add(snapshot)
            db.add(
                AuditLog(
                    user_id=actor,
                    action="backup.restore",
                    subject=snapshot.id if snapshot else "independent",
                )
            )
        if snapshot:
            print(f"Respaldo previo: {snapshot.filename}")
        print("Restauración verificada.")


if __name__ == "__main__":
    main()
