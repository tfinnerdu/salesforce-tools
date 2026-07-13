"""Tests for services.bulk_ops — query preview, bulk delete/modify/reassign, export.

Each test patches `get_sf` in the bulk_ops namespace with a `unittest.mock`
double configured to return the Salesforce response shape that test needs.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import bulk_ops


# ── Fakes ─────────────────────────────────────────────────────────────────────

def _fake_query_sf(records):
    """SF double whose query()/query_all() return the given records."""
    sf = MagicMock()
    payload = {'records': records, 'totalSize': len(records), 'done': True}
    sf.query.return_value = payload
    sf.query_all.return_value = payload
    return sf


class _FakeBulk2Object:
    def __init__(self, processed, failed):
        self._processed = processed
        self._failed = failed

    def _job(self, total):
        return [{'numberRecordsTotal': total,
                 'numberRecordsProcessed': self._processed,
                 'numberRecordsFailed': self._failed,
                 'job_id': 'JOB1'}]

    def insert(self, records=None, **kw):
        return self._job(len(records))

    def update(self, records=None, **kw):
        return self._job(len(records))

    def delete(self, csv_file=None, **kw):
        import csv as _csv
        with open(csv_file, newline='') as fh:
            rows = list(_csv.reader(fh))
        return self._job(len(rows) - 1)


class _FakeBulk2:
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return self._obj


def _fake_bulk_sf(records, processed, failed):
    """SF double exposing query_all() + a bulk2 stub."""
    sf = MagicMock()
    sf.query_all.return_value = {'records': records, 'done': True}
    sf.bulk2 = _FakeBulk2(_FakeBulk2Object(processed, failed))
    return sf


_ACCOUNT_ROWS = [
    {'attributes': {'type': 'Account'}, 'Id': '001AAA', 'Name': 'Acme'},
    {'attributes': {'type': 'Account'}, 'Id': '001BBB', 'Name': 'Globex'},
]


# ── query_preview ─────────────────────────────────────────────────────────────

def test_query_preview_returns_columns_and_rows():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(_ACCOUNT_ROWS)):
        result = bulk_ops.query_preview('dev', 'SELECT Id, Name FROM Account LIMIT 5')
    assert 'columns' in result
    assert 'rows' in result
    assert 'total' in result
    assert 'attributes' not in result['columns']
    assert result['total'] == 2


def test_query_preview_injects_limit_when_absent():
    """A query without LIMIT gets one injected so previews stay bounded."""
    sf = _fake_query_sf(_ACCOUNT_ROWS)
    with patch('services.bulk_ops.get_sf', return_value=sf):
        result = bulk_ops.query_preview('dev', 'SELECT Id FROM Account', limit=7)
    assert isinstance(result['rows'], list)
    soql_used = sf.query.call_args[0][0]
    assert 'LIMIT 7' in soql_used


# ── Delete ────────────────────────────────────────────────────────────────────

def test_bulk_delete_preview_runs():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(_ACCOUNT_ROWS)):
        result = bulk_ops.bulk_delete_preview('dev', 'Account', 'SIS_ID__c = null')
    assert 'rows' in result and 'total' in result


def test_bulk_delete_execute_counts_succeeded_and_failed():
    sf = _fake_bulk_sf([{'Id': '001AAA'}, {'Id': '001BBB'}], processed=2, failed=1)
    with patch('services.bulk_ops.get_sf', return_value=sf):
        result = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id != null')
    assert result['deleted'] == 1
    assert result['errors'] == 1
    assert result['total'] == 2
    assert result['truncated'] is False   # 2 < 10k cap


def test_bulk_delete_execute_flags_truncation(monkeypatch):
    """When the fetch hits the cap, the result flags truncation so the operator
    knows more records may match than were acted on."""
    monkeypatch.setattr(bulk_ops, '_MAX_BULK_ROWS', 2)
    sf = _fake_bulk_sf([{'Id': '001AAA'}, {'Id': '001BBB'}], processed=2, failed=0)
    with patch('services.bulk_ops.get_sf', return_value=sf):
        result = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id != null')
    assert result['truncated'] is True
    assert result['cap'] == 2


# ── Modify ────────────────────────────────────────────────────────────────────

def test_bulk_modify_preview_runs():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(_ACCOUNT_ROWS)):
        result = bulk_ops.bulk_modify_preview('dev', 'Account', 'Id != null', 'Name', 'X')
    assert 'rows' in result


def test_bulk_modify_execute_counts_updated():
    sf = _fake_bulk_sf([{'Id': '001AAA'}, {'Id': '001BBB'}], processed=2, failed=0)
    with patch('services.bulk_ops.get_sf', return_value=sf):
        result = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id != null',
                                              {'Name': 'Updated'})
    assert result['updated'] == 2
    assert result['errors'] == 0


# ── Reassign ──────────────────────────────────────────────────────────────────

def test_search_users_returns_list():
    user_rows = [{'Id': '005AAA', 'Name': 'Pat Admin', 'Username': 'pat@doane.edu'}]
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(user_rows)):
        users = bulk_ops.search_users('dev', '')
    assert isinstance(users, list)
    assert users[0]['id'] == '005AAA'
    assert users[0]['name'] == 'Pat Admin'


def test_bulk_reassign_preview_runs():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(_ACCOUNT_ROWS)):
        result = bulk_ops.bulk_reassign_preview('dev', 'Account', 'Id != null')
    assert 'rows' in result


def test_bulk_reassign_execute_counts_reassigned():
    sf = _fake_bulk_sf([{'Id': '001AAA'}], processed=1, failed=0)
    with patch('services.bulk_ops.get_sf', return_value=sf):
        result = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id != null',
                                                '005000000000000001')
    assert result['reassigned'] == 1
    assert result['errors'] == 0


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_to_csv_returns_csv_string():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf(_ACCOUNT_ROWS)):
        csv_text = bulk_ops.export_to_csv('dev', 'SELECT Id, Name FROM Account LIMIT 3')
    assert isinstance(csv_text, str)
    assert len(csv_text) > 0
    header = csv_text.splitlines()[0]
    assert 'Id' in header
    # attributes is stripped from export columns
    assert 'attributes' not in header


def test_export_to_csv_empty_result_returns_empty_string():
    with patch('services.bulk_ops.get_sf', return_value=_fake_query_sf([])):
        assert bulk_ops.export_to_csv('dev', 'SELECT Id FROM Account') == ''
