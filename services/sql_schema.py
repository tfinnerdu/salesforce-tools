"""SQL Server schema cache — table/column structure for the Join Builder.

The structure is cached (in Postgres) so the Join Builder can still compose
and validate queries when the live ODBC / Devart link is down. Colleague's
schema changes rarely, so an occasional manual refresh is enough.
"""
import json
import logging
from datetime import datetime, timezone

from config import Config

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS sql_schema_cache (
    id          INTEGER PRIMARY KEY,
    captured_at TIMESTAMPTZ DEFAULT NOW(),
    table_count INTEGER DEFAULT 0,
    schema_json JSONB NOT NULL DEFAULT '{}'
);
"""

# A small Colleague-shaped schema used in mock mode so the Join Builder is
# usable in dev without a SQL Server connection.
_MOCK_SCHEMA = {
    'dbo.STUDENTS': ['STUDENTS_ID', 'STU_ACAD_LEVELS', 'STU_TYPES', 'STU_CLASS'],
    'dbo.PERSON': ['PERSON_ID', 'FIRST_NAME', 'LAST_NAME', 'PREFERRED_NAME', 'BIRTH_DATE'],
    'dbo.STUDENT_TERMS': ['STUDENT_TERMS_ID', 'STTR_STUDENT', 'STTR_TERM', 'STTR_STATUS'],
    'dbo.APPLICATIONS': ['APPLICATIONS_ID', 'APPL_APPLICANT', 'APPL_START_TERM', 'APPL_STATUS'],
    'dbo.ADDRESS': ['ADDRESS_ID', 'ADDRESS_LINES', 'CITY', 'STATE', 'ZIP'],
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_table() -> None:
    from db import get_cursor
    with get_cursor() as cur:
        cur.execute(_DDL)


def _store(schema: dict) -> bool:
    """Persist the schema dict. Returns True if written, False if no DB."""
    try:
        from db import get_cursor, db_available
        if not db_available():
            return False
        _ensure_table()
        with get_cursor() as cur:
            cur.execute("DELETE FROM sql_schema_cache")
            cur.execute(
                "INSERT INTO sql_schema_cache (id, captured_at, table_count, schema_json) "
                "VALUES (1, %s, %s, %s)",
                (datetime.now(timezone.utc), len(schema), json.dumps(schema)),
            )
        return True
    except Exception as exc:
        logger.warning('sql_schema _store failed: %s', exc)
        return False


def _read() -> dict:
    """Read the cached schema from the DB, or {} when unavailable/empty."""
    try:
        from db import get_cursor, db_available
        if not db_available():
            return {}
        _ensure_table()
        with get_cursor() as cur:
            cur.execute("SELECT captured_at, table_count, schema_json "
                        "FROM sql_schema_cache ORDER BY captured_at DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return {}
        raw = row['schema_json']
        tables = raw if isinstance(raw, dict) else json.loads(raw or '{}')
        captured = row['captured_at']
        return {
            'captured_at': captured.isoformat() if hasattr(captured, 'isoformat') else str(captured),
            'table_count': int(row['table_count'] or 0),
            'tables': tables,
        }
    except Exception as exc:
        logger.warning('sql_schema _read failed: %s', exc)
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def get_cached_schema() -> dict:
    """Return {captured_at, table_count, tables: {name: [columns]}}.

    Falls back to a small mock schema in mock mode so the Join Builder is
    usable in dev; returns an empty schema on a real org with no cache yet.
    """
    cached = _read()
    if cached.get('tables'):
        return cached
    if Config.SF_MOCK:
        return {'captured_at': None, 'table_count': len(_MOCK_SCHEMA),
                'tables': dict(_MOCK_SCHEMA), 'mock': True}
    return {'captured_at': None, 'table_count': 0, 'tables': {}}


def _friendly_odbc_error(exc: Exception) -> str:
    """Turn a raw pyodbc error into an actionable message for the admin.

    The schema cache exists precisely so the Join Builder keeps working when
    the live link is down, so every message here ends by reassuring the user
    that the last cached schema is still in use.
    """
    text = str(exc)
    tail = 'The last cached schema is still in use.'
    if 'IM002' in text:
        return ('SQL Server ODBC driver not found on this server. Install the '
                'Microsoft ODBC Driver for SQL Server, or add an explicit '
                'DRIVER={...} clause to SQLSERVER_CONN, then retry. '
                f'{tail} [IM002]')
    if 'IM003' in text or 'specified driver could not be loaded' in text.lower():
        return ('The ODBC driver named in SQLSERVER_CONN is registered but could '
                f'not be loaded (architecture or install issue). {tail} [IM003]')
    if 'Login failed' in text or '28000' in text:
        return f'SQL Server rejected the credentials in SQLSERVER_CONN. {tail}'
    if 'timeout' in text.lower() or 'HYT00' in text or 'HYT01' in text:
        return f'SQL Server did not respond before the connection timed out. {tail}'
    return f'SQL Server refresh failed: {text}. {tail}'


def _ensure_driver(conn_str: str) -> str:
    """Prepend an installed SQL Server ODBC driver when the connection string
    names neither a DRIVER nor a DSN.

    A generic 'server=...;database=...;user id=...;password=...' string omits
    the driver, so pyodbc fails with IM002. Most admins write the string this
    way, so detect an installed driver and prepend it rather than failing.
    """
    import pyodbc  # noqa: lazy — only needed for a live refresh
    lowered = conn_str.lower()
    if 'driver=' in lowered or 'dsn=' in lowered:
        return conn_str
    sql_drivers = [d for d in pyodbc.drivers() if 'sql server' in d.lower()]
    if not sql_drivers:
        return conn_str  # none installed — let pyodbc raise its own IM002
    # Prefer the highest-numbered "ODBC Driver NN for SQL Server".
    odbc = sorted((d for d in sql_drivers if 'odbc driver' in d.lower()), reverse=True)
    driver = odbc[0] if odbc else sql_drivers[0]
    return f'DRIVER={{{driver}}};{conn_str}'


def refresh_schema() -> dict:
    """Re-introspect the SQL Server schema and cache it.

    Returns {table_count, captured_at, persisted}. In mock mode this caches
    the mock schema; otherwise it queries INFORMATION_SCHEMA.COLUMNS.
    """
    if Config.SF_MOCK:
        schema = dict(_MOCK_SCHEMA)
    else:
        conn_str = Config.SQLSERVER_CONN
        if not conn_str:
            raise ValueError('SQLSERVER_CONN is not configured — cannot refresh SQL schema')
        try:
            import pyodbc  # noqa: imported lazily — only needed for a live refresh
        except ImportError:
            raise RuntimeError(
                'The pyodbc package is not installed on this server, so the SQL '
                'Server schema cannot be refreshed. The last cached schema is '
                'still in use.'
            )
        try:
            conn = pyodbc.connect(_ensure_driver(conn_str), timeout=15)
        except pyodbc.Error as exc:
            raise RuntimeError(_friendly_odbc_error(exc)) from exc
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
            )
            schema: dict = {}
            for sch, tbl, col in cur.fetchall():
                schema.setdefault(f'{sch}.{tbl}', []).append(col)
        finally:
            conn.close()

    persisted = _store(schema)
    return {
        'table_count': len(schema),
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'persisted': persisted,
    }


def get_table_columns(table_name: str) -> list:
    """Return the cached column list for a table (case-insensitive match)."""
    tables = get_cached_schema().get('tables', {})
    if table_name in tables:
        return tables[table_name]
    lowered = table_name.lower()
    for name, cols in tables.items():
        if name.lower() == lowered:
            return cols
    return []


def validate_fields(table_name: str, fields: list) -> dict:
    """Check that ``fields`` exist on ``table_name`` per the cached schema.

    Returns {known, unknown, table_known}. When the table is not in the cache
    at all, table_known is False and nothing is flagged (cache may be stale).
    """
    columns = get_table_columns(table_name)
    if not columns:
        return {'known': [], 'unknown': [], 'table_known': False}
    col_lower = {c.lower() for c in columns}
    known, unknown = [], []
    for f in fields:
        (known if f.lower() in col_lower else unknown).append(f)
    return {'known': known, 'unknown': unknown, 'table_known': True}
