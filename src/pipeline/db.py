"""
Database connection management for StockSense.
Uses SQLAlchemy with a connection pool sized for Airflow task concurrency.
Includes startup retry logic for container environments where the DB
may not be ready immediately when the app starts.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None

_STARTUP_RETRIES = 10
_STARTUP_RETRY_DELAY = 3  # seconds between retries


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


def wait_for_db() -> None:
    """
    Block until the database is reachable or retries are exhausted.

    Called once at application startup to handle the race condition where
    the app container starts before PostgreSQL is ready to accept connections.
    Raises RuntimeError if the DB is not reachable after all retries.
    """
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database is ready (attempt %d/%d)", attempt, _STARTUP_RETRIES)
            return
        except OperationalError as exc:
            if attempt == _STARTUP_RETRIES:
                raise RuntimeError(
                    f"Database not reachable after {_STARTUP_RETRIES} attempts"
                ) from exc
            logger.warning(
                "Database not ready (attempt %d/%d), retrying in %ds: %s",
                attempt,
                _STARTUP_RETRIES,
                _STARTUP_RETRY_DELAY,
                exc,
            )
            time.sleep(_STARTUP_RETRY_DELAY)


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
