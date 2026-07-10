"""Tests for services.sqlserver — shared SQL Server connectivity helpers."""
import sys
import types

import pytest

from config import Config
from services import sqlserver


# ── normalize_keywords / ensure_driver ───────────────────────────────────────

class TestNormalizeKeywords:
    def test_translates_net_style(self):
        out = sqlserver.normalize_keywords(
            'Data Source=srv;Initial Catalog=db;User ID=svc;Password=p')
        assert 'SERVER=srv' in out
        assert 'DATABASE=db' in out
        assert 'UID=svc' in out
        assert 'PWD=p' in out
        assert 'Data Source' not in out

    def test_user_id_case_variants(self):
        out = sqlserver.normalize_keywords('user Id=svc;Password=p')
        assert 'UID=svc' in out and 'PWD=p' in out


class TestEnsureDriver:
    def test_prepends_highest_ms_driver(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyodbc', types.SimpleNamespace(
            drivers=lambda: ['SQL Server', 'ODBC Driver 17 for SQL Server',
                             'ODBC Driver 18 for SQL Server']))
        out = sqlserver.ensure_driver('server=db1;database=Colleague;user id=s;password=p')
        assert out.startswith('DRIVER={ODBC Driver 18 for SQL Server};')

    def test_leaves_explicit_driver(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyodbc',
                            types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
        conn = 'DRIVER={ODBC Driver 18 for SQL Server};server=db1'
        assert sqlserver.ensure_driver(conn) == conn

    def test_leaves_dsn_string(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyodbc',
                            types.SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server']))
        conn = 'DSN=Colleague;uid=s;pwd=p'
        assert sqlserver.ensure_driver(conn) == conn


# ── friendly_error ───────────────────────────────────────────────────────────

class TestFriendlyError:
    def test_im002(self):
        assert 'ODBC Driver' in sqlserver.friendly_error(Exception('IM002 ...'))

    def test_login(self):
        assert 'credentials' in sqlserver.friendly_error(Exception('Login failed for user'))

    def test_08001(self):
        assert 'SERVER' in sqlserver.friendly_error(Exception('08001 Neither DSN nor SERVER'))

    def test_fallback_keeps_raw(self):
        assert 'something odd' in sqlserver.friendly_error(Exception('something odd'))


# ── assert_read_only ─────────────────────────────────────────────────────────

class TestAssertReadOnly:
    @pytest.mark.parametrize('sql', [
        'SELECT * FROM dbo.PTAT',
        '  select id from x',
        'WITH cte AS (SELECT 1) SELECT * FROM cte',
        '(SELECT 1)',
    ])
    def test_allows_reads(self, sql):
        sqlserver.assert_read_only(sql)  # no raise

    @pytest.mark.parametrize('sql', [
        'DELETE FROM dbo.PTAT',
        'UPDATE x SET a=1',
        'INSERT INTO x VALUES (1)',
        'DROP TABLE x',
        'TRUNCATE TABLE x',
        'EXEC sp_who',
        "SELECT 1; DELETE FROM x",   # piggybacked write
    ])
    def test_rejects_writes(self, sql):
        with pytest.raises(ValueError):
            sqlserver.assert_read_only(sql)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match='empty'):
            sqlserver.assert_read_only('   ')


# ── connect / run_query ──────────────────────────────────────────────────────

class TestConnect:
    def test_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(Config, 'SQLSERVER_CONN', '')
        with pytest.raises(ValueError, match='not configured'):
            sqlserver.connect()

    def test_connection_error_wrapped_friendly(self, monkeypatch):
        monkeypatch.setattr(Config, 'SQLSERVER_CONN',
                            'DRIVER={ODBC Driver 18 for SQL Server};SERVER=db1')

        class _Err(Exception):
            pass

        def _boom(*a, **kw):
            raise _Err('Login failed for user')

        monkeypatch.setitem(sys.modules, 'pyodbc', types.SimpleNamespace(
            connect=_boom, Error=_Err,
            drivers=lambda: ['ODBC Driver 18 for SQL Server']))
        with pytest.raises(RuntimeError, match='credentials'):
            sqlserver.connect()


class TestRunQuery:
    def test_returns_list_of_dicts(self, monkeypatch):
        monkeypatch.setattr(Config, 'SQLSERVER_CONN',
                            'DRIVER={ODBC Driver 18 for SQL Server};SERVER=db1')

        class FakeCursor:
            description = [('TERMS_ID',), ('NAME',)]
            def execute(self, sql, params): self._sql = sql
            def fetchmany(self, n):
                return [('23/AUTM', 'Autumn'), ('24/SPR', 'Spring')]

        class FakeConn:
            def cursor(self): return FakeCursor()
            def close(self): self.closed = True

        conn = FakeConn()
        monkeypatch.setitem(sys.modules, 'pyodbc', types.SimpleNamespace(
            connect=lambda *a, **kw: conn, Error=Exception,
            drivers=lambda: ['ODBC Driver 18 for SQL Server']))

        rows = sqlserver.run_query('SELECT TERMS_ID, NAME FROM dbo.TERMS')
        assert rows == [
            {'TERMS_ID': '23/AUTM', 'NAME': 'Autumn'},
            {'TERMS_ID': '24/SPR', 'NAME': 'Spring'},
        ]

    def test_empty_description_returns_empty(self, monkeypatch):
        monkeypatch.setattr(Config, 'SQLSERVER_CONN',
                            'DRIVER={ODBC Driver 18 for SQL Server};SERVER=db1')

        class FakeCursor:
            description = None
            def execute(self, sql, params): pass

        class FakeConn:
            def cursor(self): return FakeCursor()
            def close(self): pass

        monkeypatch.setitem(sys.modules, 'pyodbc', types.SimpleNamespace(
            connect=lambda *a, **kw: FakeConn(), Error=Exception,
            drivers=lambda: ['ODBC Driver 18 for SQL Server']))
        assert sqlserver.run_query('SELECT 1 WHERE 1=0') == []
