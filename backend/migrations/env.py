from alembic import context

from app import pos_models
from app.config import Settings
from app.db import database_engine


def run_migrations():
    engine = database_engine(Settings())
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            context.configure(
                connection=connection,
                target_metadata=pos_models.metadata,
                render_as_batch=True,
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("La migración requiere conexión a SQLite")

run_migrations()
