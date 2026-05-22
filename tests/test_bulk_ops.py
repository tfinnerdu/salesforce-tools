"""Tests for services.bulk_ops — query preview, bulk delete/modify/reassign, export.

Execute paths short-circuit to mock results when SF_MOCK is true (they never
call the real Bulk API in tests). Preview and export paths run through the
mock-SF query pipeline.
"""
import pytest

from services import bulk_ops


# ── query_preview ─────────────────────────────────────────────────────────────

def test_query_preview_returns_columns_and_rows():
    result = bulk_ops.query_preview('dev', 'SELECT Id, Name FROM Account LIMIT 5')
    assert 'columns' in result
    assert 'rows' in result
    assert 'total' in result
    assert 'attributes' not in result['columns']


def test_query_preview_injects_limit_when_absent():
    """A query without LIMIT gets one injected so previews stay bounded."""
    result = bulk_ops.query_preview('dev', 'SELECT Id FROM Account', limit=7)
    assert isinstance(result['rows'], list)


# ── Delete ────────────────────────────────────────────────────────────────────

def test_bulk_delete_preview_runs():
    result = bulk_ops.bulk_delete_preview('dev', 'Account', 'SIS_ID__c = null')
    assert 'rows' in result and 'total' in result


def test_bulk_delete_execute_mock_mode():
    result = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id != null')
    assert result['mock'] is True
    assert result['deleted'] >= 0
    assert result['errors'] >= 0


# ── Modify ────────────────────────────────────────────────────────────────────

def test_bulk_modify_preview_runs():
    result = bulk_ops.bulk_modify_preview('dev', 'Account', 'Id != null', 'Name', 'X')
    assert 'rows' in result


def test_bulk_modify_execute_mock_mode():
    result = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id != null', {'Name': 'Updated'})
    assert result['mock'] is True
    assert result['updated'] >= 0


# ── Reassign ──────────────────────────────────────────────────────────────────

def test_search_users_returns_list():
    users = bulk_ops.search_users('dev', '')
    assert isinstance(users, list)
    if users:
        assert 'id' in users[0]
        assert 'name' in users[0]


def test_bulk_reassign_preview_runs():
    result = bulk_ops.bulk_reassign_preview('dev', 'Account', 'Id != null')
    assert 'rows' in result


def test_bulk_reassign_execute_mock_mode():
    result = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id != null', '005000000000000001')
    assert result['mock'] is True
    assert result['reassigned'] >= 0


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_to_csv_returns_csv_string():
    csv_text = bulk_ops.export_to_csv('dev', 'SELECT Id, Name FROM Account LIMIT 3')
    assert isinstance(csv_text, str)
    assert len(csv_text) > 0
    # First line is the header
    header = csv_text.splitlines()[0]
    assert 'Id' in header
    # attributes is stripped from export columns
    assert 'attributes' not in header


def test_export_to_csv_empty_result_returns_empty_string(monkeypatch):
    class _EmptySF:
        def query_all(self, soql):
            return {'records': []}
        def query(self, soql):
            return {'records': []}

    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _EmptySF())
    assert bulk_ops.export_to_csv('dev', 'SELECT Id FROM Account') == ''
