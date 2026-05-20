"""Tests for Apex Job Queue and Login History service functions and routes."""
import pytest


# ── Service: get_apex_job_queue ────────────────────────────────────────────────

def test_get_apex_job_queue_returns_list(mock_sf):
    from services.admin_service import get_apex_job_queue
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_apex_job_queue('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_apex_job_queue_entry_keys(mock_sf):
    from services.admin_service import get_apex_job_queue
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_apex_job_queue('dev')
    for job in result:
        assert 'id' in job
        assert 'class_name' in job
        assert 'status' in job
        assert 'status_flag' in job
        assert 'items_processed' in job
        assert 'errors' in job


def test_get_apex_job_queue_failed_status_flag():
    from services.admin_service import _job_status_flag, _mock_apex_jobs
    assert _job_status_flag('Failed') == 'danger'
    # Also verify that the mock data itself contains a Failed job with danger flag
    mock_jobs = _mock_apex_jobs()
    failed_jobs = [j for j in mock_jobs if j['status'] == 'Failed']
    assert len(failed_jobs) > 0
    for job in failed_jobs:
        assert job['status_flag'] == 'danger'


# ── Service: get_login_history ─────────────────────────────────────────────────

def test_get_login_history_returns_dict_with_expected_keys(mock_sf):
    from services.admin_service import get_login_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_login_history('dev')
    assert isinstance(result, dict)
    assert 'logins' in result
    assert 'summary' in result


def test_get_login_history_summary_keys(mock_sf):
    from services.admin_service import get_login_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_login_history('dev')
    summary = result['summary']
    assert 'total' in summary
    assert 'failed' in summary
    assert 'unique_ips' in summary
    assert 'unique_users' in summary


def test_get_login_history_failed_count_positive(mock_sf):
    from services.admin_service import get_login_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_login_history('dev')
    assert result['summary']['failed'] > 0


def test_get_login_history_failed_logins_have_success_false(mock_sf):
    from services.admin_service import get_login_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_login_history('dev')
    for login in result['logins']:
        if login['status'] != 'Success':
            assert login['success'] is False


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_job_queue_route_200(session_client):
    response = session_client.get('/admin/job-queue')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_job_queue_route_data_is_list(session_client):
    response = session_client.get('/admin/job-queue')
    data = response.get_json()
    assert isinstance(data['data'], list)


def test_login_history_route_200(session_client):
    response = session_client.get('/admin/login-history')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_login_history_route_has_logins_and_summary(session_client):
    response = session_client.get('/admin/login-history')
    data = response.get_json()
    assert 'logins' in data['data']
    assert 'summary' in data['data']


def test_job_queue_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            'services.admin_service.get_apex_job_queue',
            lambda org, limit=100: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/job-queue')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False


def test_login_history_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            'services.admin_service.get_login_history',
            lambda org: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/login-history')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
