"""Tests for services.sql_schema and the Join Builder schema-cache routes."""
import pytest

from services import sql_schema


# ── Service: cached schema (mock mode, no DB) ─────────────────────────────────

def test_get_cached_schema_returns_mock_in_mock_mode():
    """With SF_MOCK on and no DB, the cache falls back to the mock schema."""
    schema = sql_schema.get_cached_schema()
    assert schema['table_count'] >= 1
    assert isinstance(schema['tables'], dict)
    assert 'dbo.PERSON' in schema['tables']


def test_refresh_schema_mock_mode():
    """refresh_schema in mock mode caches the mock schema and reports a count."""
    result = sql_schema.refresh_schema()
    assert result['table_count'] >= 1
    assert 'captured_at' in result
    # No DB in the test env — not persisted, but still reported.
    assert result['persisted'] is False


def test_get_table_columns_case_insensitive():
    cols = sql_schema.get_table_columns('DBO.person')
    assert 'FIRST_NAME' in cols
    assert sql_schema.get_table_columns('nonexistent.table') == []


# ── Service: validate_fields ──────────────────────────────────────────────────

def test_validate_fields_flags_unknown_columns():
    result = sql_schema.validate_fields('dbo.PERSON', ['FIRST_NAME', 'BOGUS_COL'])
    assert result['table_known'] is True
    assert 'FIRST_NAME' in result['known']
    assert 'BOGUS_COL' in result['unknown']


def test_validate_fields_case_insensitive():
    result = sql_schema.validate_fields('dbo.PERSON', ['first_name', 'LAST_NAME'])
    assert result['unknown'] == []


def test_validate_fields_unknown_table_flags_nothing():
    """An uncached table is reported table_known=False and flags nothing
    (the cache may simply be stale)."""
    result = sql_schema.validate_fields('dbo.NOT_CACHED', ['ANYTHING'])
    assert result['table_known'] is False
    assert result['unknown'] == []


# ── Routes ────────────────────────────────────────────────────────────────────

def test_sql_schema_route_lists_tables(client):
    resp = client.get('/data-ops/sql-schema')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data']['tables'], list)
    assert body['data']['table_count'] >= 1


def test_sql_schema_route_returns_table_columns(client):
    resp = client.get('/data-ops/sql-schema?table=dbo.PERSON')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'FIRST_NAME' in body['data']['columns']


def test_sql_schema_refresh_route(client):
    resp = client.post('/data-ops/sql-schema/refresh')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['table_count'] >= 1


def test_sf_objects_route(client):
    resp = client.get('/data-ops/sf-objects')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_sf_object_fields_route(client):
    resp = client.get('/data-ops/sf-object-fields?object=Account')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_sf_object_fields_requires_object(client):
    resp = client.get('/data-ops/sf-object-fields')
    assert resp.status_code == 400


def test_sql_schema_refresh_error_returns_500(client, monkeypatch):
    import services.sql_schema as ss
    monkeypatch.setattr(ss, 'refresh_schema',
                        lambda: (_ for _ in ()).throw(RuntimeError('odbc down')))
    resp = client.post('/data-ops/sql-schema/refresh')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False


# ── Friendly ODBC error messages ──────────────────────────────────────────────

def test_friendly_odbc_error_im002_is_actionable():
    """A missing-driver IM002 error is rephrased into an admin-actionable hint
    that also reassures the user the cache is still usable."""
    msg = sql_schema._friendly_odbc_error(
        Exception("('IM002', '[IM002] [Microsoft][ODBC Driver Manager] "
                   "Data source name not found and no default driver specified')")
    )
    assert 'ODBC Driver' in msg
    assert 'cached schema is still in use' in msg
    assert 'IM002' in msg


def test_friendly_odbc_error_login_failure():
    msg = sql_schema._friendly_odbc_error(Exception('Login failed for user'))
    assert 'credentials' in msg
    assert 'cached schema is still in use' in msg


# ── ODBC driver auto-detection ────────────────────────────────────────────────

def test_ensure_driver_prepends_when_connection_string_omits_one(monkeypatch):
    """A driverless connection string gets an installed SQL Server driver prepended.

    A generic 'server=...;database=...;user id=...;password=...' string has no
    DRIVER clause, which is what triggers the IM002 error.
    """
    import sys
    import types
    fake_pyodbc = types.SimpleNamespace(
        drivers=lambda: ['SQL Server', 'ODBC Driver 17 for SQL Server',
                         'ODBC Driver 18 for SQL Server'])
    monkeypatch.setitem(sys.modules, 'pyodbc', fake_pyodbc)
    out = sql_schema._ensure_driver('server=db1;database=Colleague;user id=svc;password=p')
    assert out.startswith('DRIVER={ODBC Driver 18 for SQL Server};')
    assert 'server=db1' in out


def test_ensure_driver_leaves_an_explicit_driver_untouched(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'pyodbc',
                        types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
    conn = 'DRIVER={ODBC Driver 18 for SQL Server};server=db1;database=Colleague'
    assert sql_schema._ensure_driver(conn) == conn


def test_ensure_driver_leaves_a_dsn_string_untouched(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'pyodbc',
                        types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
    conn = 'DSN=ColleagueProd;uid=svc;pwd=p'
    assert sql_schema._ensure_driver(conn) == conn


def test_friendly_odbc_error_falls_back_to_raw_text():
    msg = sql_schema._friendly_odbc_error(Exception('something obscure'))
    assert 'something obscure' in msg
    assert 'cached schema is still in use' in msg


# ── NOLOCK in the generated SQL ───────────────────────────────────────────────

def test_generated_sql_uses_nolock():
    """The Join Builder output must carry WITH (NOLOCK) on the SQL Server side."""
    from services.join_builder import build_query
    result = build_query(
        sql_table='dbo.STUDENTS', sql_fields=['STUDENTS_ID'],
        sf_object='Account', sf_fields=['Id'],
        join_mapping={'sql_field': 'STUDENTS_ID', 'sf_field': 'SIS_ID__c'},
    )
    assert 'WITH (NOLOCK)' in result['openquery_sql']
    assert 'WITH (NOLOCK)' in result['sql_only']
