"""Tests for Apex Job Queue and Login History service functions and routes."""
from unittest.mock import MagicMock, patch

import pytest


def _query_sf(records):
    sf = MagicMock()
    sf.query.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_APEX_JOB_ROWS = [
    {'Id': '707000000000001', 'JobType': 'BatchApex', 'Status': 'Completed',
     'CreatedDate': '2026-05-22T08:00:00.000+0000', 'CompletedDate': '2026-05-22T08:05:00.000+0000',
     'NumberOfErrors': 0, 'JobItemsProcessed': 50, 'TotalJobItems': 50, 'ExtendedStatus': None,
     'ApexClass': {'Name': 'NightlySyncBatch'}, 'CreatedBy': {'Name': 'Todd Finner'}},
    {'Id': '707000000000002', 'JobType': 'Queueable', 'Status': 'Failed',
     'CreatedDate': '2026-05-22T09:00:00.000+0000', 'CompletedDate': '2026-05-22T09:01:00.000+0000',
     'NumberOfErrors': 3, 'JobItemsProcessed': 7, 'TotalJobItems': 10,
     'ExtendedStatus': 'First error: NullPointerException',
     'ApexClass': {'Name': 'ContactPointFixer'}, 'CreatedBy': {'Name': 'Admin User'}},
    {'Id': '707000000000003', 'JobType': 'ScheduledApex', 'Status': 'Queued',
     'CreatedDate': '2026-05-22T10:00:00.000+0000', 'CompletedDate': None,
     'NumberOfErrors': 0, 'JobItemsProcessed': 0, 'TotalJobItems': 0, 'ExtendedStatus': None,
     'ApexClass': {'Name': 'ReadinessScheduler'}, 'CreatedBy': {'Name': 'Todd Finner'}},
]


# ── Service: get_apex_job_queue ────────────────────────────────────────────────

def test_get_apex_job_queue_returns_list():
    from services.admin_service import get_apex_job_queue
    with patch('services.admin_service.get_sf', return_value=_query_sf(_APEX_JOB_ROWS)):
        result = get_apex_job_queue('dev')
    assert isinstance(result, list)
    assert len(result) == 3


def test_get_apex_job_queue_entry_keys():
    from services.admin_service import get_apex_job_queue
    with patch('services.admin_service.get_sf', return_value=_query_sf(_APEX_JOB_ROWS)):
        result = get_apex_job_queue('dev')
    for job in result:
        for key in ('id', 'class_name', 'status', 'status_flag',
                    'items_processed', 'errors'):
            assert key in job


def test_get_apex_job_queue_failed_status_flag():
    """A Failed AsyncApexJob is mapped with a 'danger' status flag."""
    from services.admin_service import _job_status_flag, get_apex_job_queue
    assert _job_status_flag('Failed') == 'danger'
    with patch('services.admin_service.get_sf', return_value=_query_sf(_APEX_JOB_ROWS)):
        result = get_apex_job_queue('dev')
    failed = [j for j in result if j['status'] == 'Failed']
    assert len(failed) == 1
    for job in failed:
        assert job['status_flag'] == 'danger'
        assert job['errors'] == 3


# ── Service: get_login_history ─────────────────────────────────────────────────

_LOGIN_ROWS = [
    {'Id': '0Ya000000000001', 'UserId': '005000000000001', 'LoginTime': '2026-05-22T08:00:00.000+0000',
     'SourceIp': '10.0.0.1', 'Platform': 'Windows', 'Application': 'Browser',
     'LoginType': 'Application', 'Status': 'Success', 'Browser': 'Chrome'},
    {'Id': '0Ya000000000002', 'UserId': '005000000000002', 'LoginTime': '2026-05-22T08:30:00.000+0000',
     'SourceIp': '10.0.0.2', 'Platform': 'Mac', 'Application': 'Browser',
     'LoginType': 'Application', 'Status': 'Invalid Password', 'Browser': 'Safari'},
    {'Id': '0Ya000000000003', 'UserId': '005000000000001', 'LoginTime': '2026-05-22T09:00:00.000+0000',
     'SourceIp': '10.0.0.1', 'Platform': 'Windows', 'Application': 'API',
     'LoginType': 'Remote Access 2.0', 'Status': 'Failed: Login challenge', 'Browser': 'Unknown'},
]


def test_get_login_history_returns_dict_with_expected_keys():
    from services.admin_service import get_login_history
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
        result = get_login_history('dev')
    assert isinstance(result, dict)
    assert 'logins' in result
    assert 'summary' in result


def test_get_login_history_summary_keys():
    from services.admin_service import get_login_history
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
        result = get_login_history('dev')
    summary = result['summary']
    for key in ('total', 'failed', 'unique_ips', 'unique_users'):
        assert key in summary
    assert summary['total'] == 3
    assert summary['unique_users'] == 2
    assert summary['unique_ips'] == 2


def test_get_login_history_failed_count_positive():
    from services.admin_service import get_login_history
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
        result = get_login_history('dev')
    # Two non-Success rows in the fixture.
    assert result['summary']['failed'] == 2


def test_get_login_history_failed_logins_have_success_false():
    from services.admin_service import get_login_history
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
        result = get_login_history('dev')
    for login in result['logins']:
        if login['status'] != 'Success':
            assert login['success'] is False
        else:
            assert login['success'] is True


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_job_queue_route_200(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_APEX_JOB_ROWS)):
        response = session_client.get('/admin/job-queue')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_job_queue_route_data_is_list(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_APEX_JOB_ROWS)):
        response = session_client.get('/admin/job-queue')
    data = response.get_json()
    assert isinstance(data['data'], list)
    assert len(data['data']) == 3


def test_login_history_route_200(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
        response = session_client.get('/admin/login-history')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_login_history_route_has_logins_and_summary(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_LOGIN_ROWS)):
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
