"""Tests for services.record_lock_detector, services.bulk_job_history, and routes."""
from unittest.mock import MagicMock, patch

import pytest

from services import record_lock_detector, bulk_job_history


# ── Salesforce doubles ────────────────────────────────────────────────────────

def _query_sf(records):
    """SF double whose query() returns the given ProcessInstance records."""
    sf = MagicMock()
    sf.query.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


class _RestfulSF:
    """SF double whose restful() returns ingest-job records, or raises."""
    def __init__(self, records=None, raise_exc=None):
        self._records = records or []
        self._raise = raise_exc

    def restful(self, path, **kw):
        if self._raise:
            raise self._raise
        return {'records': self._records}


# ── record_lock_detector unit tests ──────────────────────────────────────────

def test_get_locked_records_returns_expected_keys():
    """get_locked_records returns dict with total_locked, by_object, objects_checked."""
    with patch('services.record_lock_detector.get_sf', return_value=_query_sf([])):
        result = record_lock_detector.get_locked_records(org='dev')
    assert 'total_locked' in result
    assert 'by_object' in result
    assert 'objects_checked' in result


def test_get_locked_records_counts_pending_approvals():
    """total_locked sums ProcessInstance rows across the checked objects."""
    rows = [{'Id': '04i1', 'Status': 'Pending'}, {'Id': '04i2', 'Status': 'Pending'}]
    with patch('services.record_lock_detector.get_sf', return_value=_query_sf(rows)):
        result = record_lock_detector.get_locked_records(org='dev')
    # Three default objects (Account, Opportunity, Case) each return the 2 rows.
    assert result['total_locked'] == 6
    assert set(result['by_object']) == {'Account', 'Opportunity', 'Case'}


def test_get_locked_records_with_object_filter(monkeypatch):
    """An object filter restricts the query to a single object."""
    rows = [{'Id': '04i1', 'Status': 'Pending'}]
    with patch('services.record_lock_detector.get_sf', return_value=_query_sf(rows)):
        result = record_lock_detector.get_locked_records(org='dev', sobject='Account')
    assert result['objects_checked'] == ['Account']
    assert 'Account' in result['by_object']
    assert result['total_locked'] == 1


def test_get_locked_records_query_failure_yields_empty_list():
    """A failed lock query for one object degrades to [] for that object."""
    sf = MagicMock()
    sf.query.side_effect = RuntimeError('MALFORMED_QUERY')
    with patch('services.record_lock_detector.get_sf', return_value=sf):
        result = record_lock_detector.get_locked_records(org='dev')
    assert result['total_locked'] == 0
    assert result['by_object']['Account'] == []


# ── bulk_job_history unit tests ───────────────────────────────────────────────

def test_get_bulk_jobs_returns_list():
    """get_bulk_jobs returns a list."""
    with patch('services.bulk_job_history.get_sf', return_value=_RestfulSF(records=[])):
        result = bulk_job_history.get_bulk_jobs(org='dev')
    assert isinstance(result, list)


def test_get_bulk_jobs_empty_org_returns_empty_list():
    """An empty org returns [] — never fabricated job history."""
    with patch('services.bulk_job_history.get_sf', return_value=_RestfulSF(records=[])):
        assert bulk_job_history.get_bulk_jobs(org='prod') == []


def test_get_bulk_jobs_error_propagates():
    """A Bulk API failure surfaces — it is not masked with mock data."""
    with patch('services.bulk_job_history.get_sf',
               return_value=_RestfulSF(raise_exc=RuntimeError('Bulk API 500'))):
        with pytest.raises(RuntimeError, match='Bulk API 500'):
            bulk_job_history.get_bulk_jobs(org='prod')


def test_get_bulk_jobs_maps_records():
    """Real ingest-job records are mapped to the UI shape."""
    records = [
        {'id': '750xx', 'operation': 'insert', 'object': 'Account', 'state': 'JobComplete',
         'numberRecordsProcessed': 10, 'numberRecordsFailed': 0, 'createdDate': '2026-05-01'},
        {'id': '750yy', 'operation': 'update', 'object': 'Contact', 'state': 'Failed',
         'numberRecordsProcessed': 0, 'numberRecordsFailed': 0, 'createdDate': '2026-05-02'},
    ]
    with patch('services.bulk_job_history.get_sf',
               return_value=_RestfulSF(records=records)):
        jobs = bulk_job_history.get_bulk_jobs(org='prod')
    assert len(jobs) == 2
    # Sorted newest-first by createdDate.
    assert jobs[0]['id'] == '750yy'
    assert jobs[0]['state'] == 'Failed'
    assert jobs[1]['id'] == '750xx'
    assert jobs[1]['object'] == 'Account'


# ── Route integration tests ───────────────────────────────────────────────────

def test_get_api_record_locks_returns_200(session_client):
    """GET /data-ops/api/record-locks returns 200 with success=True."""
    with patch('services.record_lock_detector.get_sf', return_value=_query_sf([])):
        resp = session_client.get('/data-ops/api/record-locks')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'total_locked' in data['data']


def test_get_api_bulk_jobs_returns_200(session_client):
    """GET /data-ops/api/bulk-jobs returns 200 with success=True."""
    with patch('services.bulk_job_history.get_sf', return_value=_RestfulSF(records=[])):
        resp = session_client.get('/data-ops/api/bulk-jobs')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_get_record_locks_page_returns_200(client):
    """GET /data-ops/record-locks renders the page with HTTP 200."""
    resp = client.get('/data-ops/record-locks')
    assert resp.status_code == 200
    assert b'Record Lock Detector' in resp.data
