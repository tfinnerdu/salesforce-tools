"""Tests for services.regression_tester — SOQL regression suite runner.

Closes a coverage gap found during the TESTING.md matrix reconciliation:
regression_tester.py previously had no test of its own. The DB layer is
stubbed; the focus is the assertion-evaluation logic in run_suite.
"""
import pytest

from services import regression_tester


# ── Stubs ─────────────────────────────────────────────────────────────────────

class _FakeCursor:
    """Minimal cursor context manager for the DB-backed functions."""
    def __init__(self, fetchone=None, fetchall=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class _StubSF:
    """Returns a fixed totalSize for every query, or raises if configured to."""
    def __init__(self, total=100, raise_exc=None):
        self._total = total
        self._raise = raise_exc

    def query(self, soql):
        if self._raise:
            raise self._raise
        return {'totalSize': self._total, 'records': []}


# ── _ensure_table / list_suites / save_suite ──────────────────────────────────

def test_ensure_table_runs(monkeypatch):
    cur = _FakeCursor()
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: cur)
    regression_tester._ensure_table()  # must not raise
    assert cur.executed


def test_ensure_table_reraises_on_db_failure(monkeypatch):
    """A DDL failure must propagate — the caller cannot proceed without the table."""
    class _BadCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **kw): raise RuntimeError('db down')

    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _BadCursor())
    with pytest.raises(RuntimeError, match='db down'):
        regression_tester._ensure_table()


def test_list_suites_returns_rows(monkeypatch):
    rows = [{'id': 1, 'name': 'Smoke', 'assertions': [], 'baseline': None, 'created_at': 'x'}]
    monkeypatch.setattr(regression_tester, 'get_cursor',
                        lambda: _FakeCursor(fetchall=rows))
    suites = regression_tester.list_suites()
    assert suites == rows


def test_save_suite_inserts_and_returns_row(monkeypatch):
    row = {'id': 7, 'name': 'New', 'assertions': '[]', 'created_at': 'x'}
    monkeypatch.setattr(regression_tester, 'get_cursor',
                        lambda: _FakeCursor(fetchone=row))
    result = regression_tester.save_suite('New', [{'label': 'A', 'soql': 'SELECT Id FROM Account'}])
    assert result['id'] == 7


# ── run_suite — assertion evaluation logic ────────────────────────────────────

def test_run_suite_not_found_raises(monkeypatch):
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=None))
    with pytest.raises(ValueError, match='not found'):
        regression_tester.run_suite('dev', 999)


def test_run_suite_expected_count_pass_and_fail(monkeypatch):
    suite = {
        'id': 1, 'name': 'Counts',
        'assertions': [
            {'label': 'matches', 'soql': 'SELECT Id FROM Account', 'expected_count': 100},
            {'label': 'mismatch', 'soql': 'SELECT Id FROM Contact', 'expected_count': 50},
        ],
        'baseline': None,
    }
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf', lambda org: _StubSF(total=100))

    result = regression_tester.run_suite('dev', 1)
    by_label = {r['label']: r for r in result['results']}
    assert by_label['matches']['status'] == 'pass'      # 100 == expected 100
    assert by_label['mismatch']['status'] == 'fail'     # 100 != expected 50
    assert result['summary']['pass'] == 1
    assert result['summary']['fail'] == 1


def test_run_suite_baseline_takes_precedence(monkeypatch):
    suite = {
        'id': 2, 'name': 'Baselined',
        'assertions': [{'label': 'drift', 'soql': 'SELECT Id FROM Account', 'expected_count': 100}],
        'baseline': {'drift': 90},   # baseline 90, actual will be 100 -> fail
    }
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf', lambda org: _StubSF(total=100))

    result = regression_tester.run_suite('dev', 2)
    assert result['results'][0]['status'] == 'fail'
    assert result['results'][0]['baseline_count'] == 90


def test_run_suite_no_baseline_no_expected_is_info(monkeypatch):
    suite = {
        'id': 3, 'name': 'Informational',
        'assertions': [{'label': 'just count', 'soql': 'SELECT Id FROM Account'}],
        'baseline': None,
    }
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf', lambda org: _StubSF(total=42))

    result = regression_tester.run_suite('dev', 3)
    assert result['results'][0]['status'] == 'info'
    assert result['results'][0]['actual_count'] == 42


def test_run_suite_query_error_is_reported(monkeypatch):
    suite = {
        'id': 4, 'name': 'Broken',
        'assertions': [{'label': 'bad', 'soql': 'SELECT bogus FROM Nothing', 'expected_count': 1}],
        'baseline': None,
    }
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf',
                        lambda org: _StubSF(raise_exc=RuntimeError('INVALID_FIELD')))

    result = regression_tester.run_suite('dev', 4)
    assert result['results'][0]['status'] == 'error'
    assert 'INVALID_FIELD' in result['results'][0]['error']
    assert result['summary']['error'] == 1


# ── save_baseline ─────────────────────────────────────────────────────────────

def test_save_baseline_captures_counts(monkeypatch):
    suite = {'id': 5, 'name': 'Base',
             'assertions': [{'label': 'A', 'soql': 'SELECT Id FROM Account'}]}
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf', lambda org: _StubSF(total=314))

    result = regression_tester.save_baseline('dev', 5)
    assert result['baseline'] == {'A': 314}


def test_save_baseline_suite_not_found_raises(monkeypatch):
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=None))
    with pytest.raises(ValueError, match='not found'):
        regression_tester.save_baseline('dev', 999)


def test_save_baseline_query_failure_records_none(monkeypatch):
    """If an assertion's query fails during baseline capture, store None for it."""
    suite = {'id': 6, 'name': 'Base',
             'assertions': [{'label': 'A', 'soql': 'SELECT bogus FROM Nothing'}]}
    monkeypatch.setattr(regression_tester, 'get_cursor', lambda: _FakeCursor(fetchone=suite))
    monkeypatch.setattr(regression_tester, 'get_sf',
                        lambda org: _StubSF(raise_exc=RuntimeError('INVALID_FIELD')))
    result = regression_tester.save_baseline('dev', 6)
    assert result['baseline'] == {'A': None}
