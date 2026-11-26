from fastapi import HTTPException
from sqlalchemy import select

from app.commercial_models import MailJob, PlatformSetting
from app.db import write_transaction
from app.models import AuditLog, now


def enqueue(db, key, recipient, subject, body, tenant_id=None):
    smtp = db.get(PlatformSetting, "smtp")
    if recipient and smtp and smtp.value.get("enabled") and not db.get(MailJob, key):
        db.add(
            MailJob(key=key, recipient=recipient, subject=subject, body=body, tenant_id=tenant_id)
        )


def admin_notice(db, key, message, tenant_id):
    config = db.get(PlatformSetting, "general")
    if config:
        enqueue(
            db,
            f"admin:{key}",
            config.value.get("notification_email"),
            "Aviso administrativo de Raíz Food",
            message,
            tenant_id,
        )


def dispatch(settings, actor_id, limit=20):
    from app.cli import connect
    from app.platform_admin import deliver, read_smtp

    for _ in range(limit):
        with connect(settings) as db, write_transaction(db):
            smtp = read_smtp(db)
            if not smtp.get("enabled"):
                return
            job = db.scalar(
                select(MailJob)
                .where(MailJob.state == "pending")
                .order_by(MailJob.created_at, MailJob.key)
                .limit(1)
            )
            if not job:
                return
            job.state = "sending"
            key, recipient, subject, body = job.key, job.recipient, job.subject, job.body
        try:
            result = deliver(settings, smtp, recipient, subject, body)
        except HTTPException:
            result = "failed"
        with connect(settings) as db, write_transaction(db):
            job = db.get(MailJob, key)
            job.state = result
            job.finished_at = now()
            db.add(
                AuditLog(
                    user_id=actor_id,
                    tenant_id=job.tenant_id,
                    action="smtp.dispatch",
                    subject="outbox",
                    result=result,
                )
            )
