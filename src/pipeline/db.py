"""
Database connection management for StockSense.
Uses SQLAlchemy with a connection pool sized for Airflow task concurrency.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        db_url = os.environ["DATABASE_URL"]
        _engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # detect stale connections
        )
    return _engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a database session and handle commit/rollback automatically."""
    session = SessionLocal(bind=get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_migrations(sql_path: str) -> None:
    """Execute a SQL migration file against the database."""
    with get_engine().connect() as conn:
        with open(sql_path) as f:
            conn.execute(text(f.read()))
        conn.commit()
