"""Tests for services.record_lock_detector, services.bulk_job_history, and related routes."""
import pytest

from services import record_lock_detector, bulk_job_history


# ── record_lock_detector unit tests ──────────────────────────────────────────

def test_get_locked_records_returns_expected_keys():
    """get_locked_records returns dict with total_locked, by_object, objects_checked."""
    result = record_lock_detector.get_locked_records(org='dev')
    assert 'total_locked' in result
    assert 'by_object' in result
    assert 'objects_checked' in result


def test_mock_locked_total_locked_is_two():
    """_mock_locked() returns total_locked == 2."""
    result = record_lock_detector._mock_locked()
    assert result['total_locked'] == 2


def test_mock_locked_with_account_filter_has_account_key():
    """_mock_locked('Account') returns by_object with Account key."""
    result = record_lock_detector._mock_locked('Account')
    assert 'Account' in result['by_object']


# ── bulk_job_history unit tests ───────────────────────────────────────────────

def test_get_bulk_jobs_returns_list():
    """get_bulk_jobs returns a list."""
    result = bulk_job_history.get_bulk_jobs(org='dev')
    assert isinstance(result, list)


def test_mock_bulk_jobs_returns_four_items():
    """_mock_bulk_jobs() returns exactly 4 items."""
    result = bulk_job_history._mock_bulk_jobs()
    assert len(result) == 4


def test_mock_bulk_jobs_bj001_is_job_complete():
    """_mock_bulk_jobs() BJ001 has state JobComplete."""
    jobs = {j['id']: j for j in bulk_job_history._mock_bulk_jobs()}
    assert jobs['BJ001']['state'] == 'JobComplete'


def test_mock_bulk_jobs_bj003_is_failed():
    """_mock_bulk_jobs() BJ003 has state Failed."""
    jobs = {j['id']: j for j in bulk_job_history._mock_bulk_jobs()}
    assert jobs['BJ003']['state'] == 'Failed'


# ── Route integration tests ───────────────────────────────────────────────────

def test_get_api_record_locks_returns_200(session_client):
    """GET /data-ops/api/record-locks returns 200 with success=True."""
    resp = session_client.get('/data-ops/api/record-locks')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'total_locked' in data['data']


def test_get_api_bulk_jobs_returns_200(session_client):
    """GET /data-ops/api/bulk-jobs returns 200 with success=True."""
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
