"""Shared SQL Server connectivity for the Colleague backend.

One home for the pyodbc connection logic so the Join Builder schema-refresh
(services/sql_schema.py) and the key-map SQL ingester (services/ingest.py)
share the same driver detection, connection-string normalisation, and error
messaging.

Uses the standard Microsoft ODBC Driver for SQL Server — there is no Devart
dependency in the app. Colleague is fronted by a SQL Server (the same one the
Join Builder already targets), so this connects to that instance via
``Config.SQLSERVER_CONN``.
"""
import logging
import re

from config import Config

logger = logging.getLogger(__name__)

# Defensive cap so a runaway query can't pull the whole warehouse into memory.
DEFAULT_MAX_ROWS = 100_000


def is_configured() -> bool:
    return bool(Config.SQLSERVER_CONN)


def normalize_keywords(conn_str: str) -> str:
    """Translate .NET-style connection-string keywords to ODBC ones.

    ADO.NET uses 'Data Source', 'User ID', 'Password', 'Initial Catalog';
    pyodbc / the ODBC driver expect 'SERVER', 'UID', 'PWD', 'DATABASE'.
    """
    pairs = [
        (r'(?i)\bData\s+Source\s*=', 'SERVER='),
        (r'(?i)\bInitial\s+Catalog\s*=', 'DATABASE='),
        (r'(?i)\bUser\s+ID\s*=', 'UID='),
        (r'(?i)\bUser\s+Id\s*=', 'UID='),
        (r'(?i)\bPassword\s*=', 'PWD='),
    ]
    for pattern, replacement in pairs:
        conn_str = re.sub(pattern, replacement, conn_str)
    return conn_str


def ensure_driver(conn_str: str) -> str:
    """Prepend an installed SQL Server ODBC driver when the connection string
    names neither a DRIVER nor a DSN, and normalise .NET-style keywords.

    Prefers the highest-numbered "ODBC Driver NN for SQL Server" (the
    Microsoft driver) — never Devart.
    """
    import pyodbc  # noqa: lazy — only needed for a live connection
    conn_str = normalize_keywords(conn_str)
    lowered = conn_str.lower()
    if 'driver=' in lowered or 'dsn=' in lowered:
        return conn_str
    sql_drivers = [d for d in pyodbc.drivers() if 'sql server' in d.lower()]
    if not sql_drivers:
        return conn_str  # none installed — let pyodbc raise its own IM002
    odbc = sorted((d for d in sql_drivers if 'odbc driver' in d.lower()), reverse=True)
    driver = odbc[0] if odbc else sql_drivers[0]
    return f'DRIVER={{{driver}}};{conn_str}'


def friendly_error(exc: Exception) -> str:
    """Turn a raw pyodbc error into an actionable message for the operator."""
    text = str(exc)
    if 'IM002' in text:
        return ('SQL Server ODBC driver not found on this server. Install the '
                'Microsoft ODBC Driver for SQL Server, or add an explicit '
                'DRIVER={...} clause to SQLSERVER_CONN, then retry. [IM002]')
    if 'IM003' in text or 'specified driver could not be loaded' in text.lower():
        return ('The ODBC driver named in SQLSERVER_CONN is registered but '
                'could not be loaded (architecture or install issue). [IM003]')
    if '08001' in text or 'Neither DSN nor SERVER' in text:
        return ('SQL Server could not connect — the SERVER name in '
                'SQLSERVER_CONN is missing or empty. Use the form: '
                'SERVER=myhost;DATABASE=mydb;UID=myuser;PWD=mypassword [08001]')
    if 'Login failed' in text or '28000' in text:
        return f'SQL Server rejected the credentials in SQLSERVER_CONN.'
    if 'timeout' in text.lower() or 'HYT00' in text or 'HYT01' in text:
        return 'SQL Server did not respond before the connection timed out.'
    return f'SQL Server query failed: {text}.'


def connect(timeout: int = 15):
    """Open a pyodbc connection to SQL Server via SQLSERVER_CONN.

    Raises ValueError when unconfigured, RuntimeError (with a friendly
    message) on driver/connection errors.
    """
    conn_str = Config.SQLSERVER_CONN
    if not conn_str:
        raise ValueError('SQLSERVER_CONN is not configured.')
    try:
        import pyodbc
    except ImportError:
        raise RuntimeError(
            'The pyodbc package is not installed on this server, so SQL Server '
            'cannot be reached.'
        )
    try:
        return pyodbc.connect(ensure_driver(conn_str), timeout=timeout)
    except pyodbc.Error as exc:
        raise RuntimeError(friendly_error(exc)) from exc


def run_query(sql: str, params=None, max_rows: int = DEFAULT_MAX_ROWS) -> list:
    """Run a SELECT and return ``list[dict]`` keyed by column name.

    Caps the result at ``max_rows`` defensively. The connection is always
    closed. Callers are responsible for ensuring ``sql`` is a read query.
    """
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        if not cur.description:
            return []
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows)
        return [{columns[i]: raw[i] for i in range(len(columns))} for raw in rows]
    finally:
        conn.close()


# Read-only guard for user-supplied SQL (the ingester runs arbitrary text).
_WRITE_TOKENS = re.compile(
    r'(?is)\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke)\b'
)


def assert_read_only(sql: str) -> None:
    """Raise ValueError if the SQL looks like anything other than a read.

    Defence in depth — the connection account should already be read-only,
    but the ingester never needs to run a write, so reject one outright.
    """
    stripped = (sql or '').strip()
    if not stripped:
        raise ValueError('SQL query is empty.')
    head = stripped.lstrip('(').lstrip()
    if not re.match(r'(?is)^(select|with)\b', head):
        raise ValueError('Only SELECT / WITH queries are allowed here.')
    if _WRITE_TOKENS.search(stripped):
        raise ValueError(
            'Query contains a write/DDL keyword (insert/update/delete/etc.) — '
            'only read queries are allowed in the ingester.'
        )
