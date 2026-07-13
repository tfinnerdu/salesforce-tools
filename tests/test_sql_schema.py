"""Tests for services.sql_schema and the Join Builder schema-cache routes.

There is no mock schema. With no DB, get_cached_schema() returns an empty
schema; refresh_schema() requires Config.SQLSERVER_CONN and uses pyodbc.
Tests that need a populated cache patch sql_schema._read with a controlled
schema dict.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from services import sql_schema


# A controlled cached-schema payload, as _read() would return it.
_CACHED = {
    'captured_at': '2026-05-01T00:00:00+00:00',
    'table_count': 2,
    'tables': {
        'dbo.PERSON': ['ID', 'FIRST_NAME', 'LAST_NAME'],
        'dbo.STUDENTS': ['STUDENTS_ID', 'PROGRAM'],
    },
}


@pytest.fixture
def cached_schema(monkeypatch):
    """Make the schema cache return a populated schema."""
    monkeypatch.setattr(sql_schema, '_read', lambda: dict(_CACHED))


# ── Service: cached schema — empty when no DB ─────────────────────────────────

def test_get_cached_schema_returns_empty_without_db():
    """With no DB and no cache, get_cached_schema returns the empty-schema shape."""
    schema = sql_schema.get_cached_schema()
    assert schema == {'captured_at': None, 'table_count': 0, 'tables': {}}


def test_get_cached_schema_returns_cache_when_present(cached_schema):
    """When the cache has tables, they are returned as-is."""
    schema = sql_schema.get_cached_schema()
    assert schema['table_count'] == 2
    assert 'dbo.PERSON' in schema['tables']


# ── Service: refresh_schema ───────────────────────────────────────────────────

def test_refresh_schema_requires_conn(monkeypatch):
    """refresh_schema raises a clear error when SQLSERVER_CONN is unset."""
    monkeypatch.setattr(sql_schema.Config, 'SQLSERVER_CONN', '')
    with pytest.raises(ValueError, match='SQLSERVER_CONN'):
        sql_schema.refresh_schema()


def test_refresh_schema_introspects_via_pyodbc(monkeypatch):
    """refresh_schema queries INFORMATION_SCHEMA.COLUMNS and reports a count."""
    monkeypatch.setattr(sql_schema.Config, 'SQLSERVER_CONN',
                        'DRIVER={ODBC Driver 18 for SQL Server};SERVER=db1;DATABASE=Colleague')

    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ('dbo', 'PERSON', 'ID'),
        ('dbo', 'PERSON', 'FIRST_NAME'),
        ('dbo', 'STUDENTS', 'STUDENTS_ID'),
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_pyodbc = types.SimpleNamespace(
        connect=lambda *a, **kw: conn,
        Error=Exception,
        drivers=lambda: ['ODBC Driver 18 for SQL Server'],
    )
    monkeypatch.setitem(sys.modules, 'pyodbc', fake_pyodbc)
    # No DB in the test env — persistence is skipped.
    monkeypatch.setattr(sql_schema, '_store', lambda schema: False)

    result = sql_schema.refresh_schema()
    assert result['table_count'] == 2          # dbo.PERSON + dbo.STUDENTS
    assert 'captured_at' in result
    assert result['persisted'] is False
    conn.close.assert_called_once()


def test_refresh_schema_wraps_odbc_error(monkeypatch):
    """A pyodbc connection failure is surfaced as a friendly RuntimeError."""
    monkeypatch.setattr(sql_schema.Config, 'SQLSERVER_CONN',
                        'DRIVER={ODBC Driver 18 for SQL Server};SERVER=db1')

    class _OdbcError(Exception):
        pass

    def _boom(*a, **kw):
        raise _OdbcError('Login failed for user')

    fake_pyodbc = types.SimpleNamespace(
        connect=_boom, Error=_OdbcError,
        drivers=lambda: ['ODBC Driver 18 for SQL Server'],
    )
    monkeypatch.setitem(sys.modules, 'pyodbc', fake_pyodbc)
    with pytest.raises(RuntimeError, match='credentials'):
        sql_schema.refresh_schema()


# ── Service: get_table_columns / validate_fields ──────────────────────────────

def test_get_table_columns_case_insensitive(cached_schema):
    cols = sql_schema.get_table_columns('DBO.person')
    assert 'FIRST_NAME' in cols
    assert sql_schema.get_table_columns('nonexistent.table') == []


def test_validate_fields_flags_unknown_columns(cached_schema):
    result = sql_schema.validate_fields('dbo.PERSON', ['FIRST_NAME', 'BOGUS_COL'])
    assert result['table_known'] is True
    assert 'FIRST_NAME' in result['known']
    assert 'BOGUS_COL' in result['unknown']


def test_validate_fields_case_insensitive(cached_schema):
    result = sql_schema.validate_fields('dbo.PERSON', ['first_name', 'LAST_NAME'])
    assert result['unknown'] == []


def test_validate_fields_unknown_table_flags_nothing(cached_schema):
    """An uncached table is reported table_known=False and flags nothing
    (the cache may simply be stale)."""
    result = sql_schema.validate_fields('dbo.NOT_CACHED', ['ANYTHING'])
    assert result['table_known'] is False
    assert result['unknown'] == []


# ── Routes ────────────────────────────────────────────────────────────────────

def test_sql_schema_route_lists_tables(client, cached_schema):
    resp = client.get('/data-ops/sql-schema')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data']['tables'], list)
    assert body['data']['table_count'] == 2


def test_sql_schema_route_empty_without_cache(client):
    """With no DB and no cache the route still succeeds with an empty schema."""
    resp = client.get('/data-ops/sql-schema')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['table_count'] == 0
    assert body['data']['tables'] == []


def test_sql_schema_route_returns_table_columns(client, cached_schema):
    resp = client.get('/data-ops/sql-schema?table=dbo.PERSON')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'FIRST_NAME' in body['data']['columns']


def test_sql_schema_refresh_route(client, monkeypatch):
    monkeypatch.setattr(sql_schema, 'refresh_schema',
                        lambda: {'table_count': 2,
                                 'captured_at': '2026-05-01T00:00:00+00:00',
                                 'persisted': False})
    resp = client.post('/data-ops/sql-schema/refresh')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['table_count'] == 2


def test_sf_object_fields_route(client, monkeypatch):
    from services import soql_workbench
    fake = MagicMock()
    fake.restful.return_value = {'fields': [
        {'name': 'Id', 'label': 'Record ID', 'type': 'id'},
    ]}
    monkeypatch.setattr(soql_workbench, 'get_sf', lambda org: fake)
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
    fake_pyodbc = types.SimpleNamespace(
        drivers=lambda: ['SQL Server', 'ODBC Driver 17 for SQL Server',
                         'ODBC Driver 18 for SQL Server'])
    monkeypatch.setitem(sys.modules, 'pyodbc', fake_pyodbc)
    out = sql_schema._ensure_driver('server=db1;database=Colleague;user id=svc;password=p')
    assert out.startswith('DRIVER={ODBC Driver 18 for SQL Server};')
    assert 'server=db1' in out


def test_ensure_driver_leaves_an_explicit_driver_untouched(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pyodbc',
                        types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
    conn = 'DRIVER={ODBC Driver 18 for SQL Server};server=db1;database=Colleague'
    assert sql_schema._ensure_driver(conn) == conn


def test_normalize_keywords_translates_net_style():
    """ADO.NET-style keywords are translated to ODBC equivalents before driver detection."""
    result = sql_schema._normalize_keywords(
        'Data Source=myserver;Initial Catalog=mydb;User ID=svc;Password=secret'
    )
    assert 'SERVER=myserver' in result
    assert 'DATABASE=mydb' in result
    assert 'UID=svc' in result
    assert 'PWD=secret' in result
    assert 'Data Source' not in result
    assert 'User ID' not in result


def test_normalize_keywords_handles_user_id_case_variants():
    r1 = sql_schema._normalize_keywords('user Id=svc;Password=p')
    assert 'UID=svc' in r1
    assert 'PWD=p' in r1


def test_ensure_driver_leaves_a_dsn_string_untouched(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pyodbc',
                        types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
    conn = 'DSN=ColleagueProd;uid=svc;pwd=p'
    assert sql_schema._ensure_driver(conn) == conn


def test_friendly_odbc_error_08001_server_missing():
    msg = sql_schema._friendly_odbc_error(
        Exception("('08001', '[08001] Neither DSN nor SERVER keyword supplied')")
    )
    assert 'SERVER' in msg
    assert 'cached schema is still in use' in msg
    assert '08001' in msg


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
