from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import BACKEND, Settings


class Base(DeclarativeBase):
    pass


def database_engine(settings: Settings):
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Indica un archivo SQLite persistente en DATABASE_URL")
    path = (BACKEND / Path(url.database)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url.set(database=str(path)), connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {settings.sqlite_busy_timeout_ms}")
            if cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                raise RuntimeError("No se pudo activar SQLite WAL")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


@contextmanager
def write_transaction(db: Session):
    # Reserve the writer before any state used to enforce an invariant is read.
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise
