import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
import psycopg2.extras

from config import Config

logger = logging.getLogger(__name__)


def get_connection() -> psycopg2.extensions.connection:
    """Open and return a raw psycopg2 connection."""
    return psycopg2.connect(Config.DATABASE_URL)


@contextmanager
def get_cursor() -> Generator[psycopg2.extras.RealDictCursor, None, None]:
    """Context manager that yields a RealDictCursor, commits on success, rolls back on error."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create required tables if they do not already exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS readiness_runs (
        id          SERIAL PRIMARY KEY,
        org         VARCHAR(50),
        run_at      TIMESTAMP DEFAULT NOW(),
        results     JSONB,
        overall_pct FLOAT
    );

    CREATE TABLE IF NOT EXISTS saved_queries (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(200),
        query       TEXT,
        created_by  VARCHAR(100),
        created_at  TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS query_history (
        id          SERIAL PRIMARY KEY,
        user_key    VARCHAR(100),
        query       TEXT,
        org         VARCHAR(50),
        ran_at      TIMESTAMP DEFAULT NOW(),
        row_count   INTEGER
    );

    CREATE TABLE IF NOT EXISTS api_collections (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(200),
        collection_json JSONB,
        created_at      TIMESTAMP DEFAULT NOW(),
        updated_at      TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        with get_cursor() as cur:
            cur.execute(ddl)
        logger.info("Database tables initialised.")
    except Exception as exc:
        logger.error("init_db failed: %s", exc)
        raise


def db_available() -> bool:
    """Return True if a DB connection can be established, False otherwise."""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False
