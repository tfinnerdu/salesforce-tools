"""Tests for services.admin_service.

Each SF-touching test patches `get_sf` in the admin_service namespace with a
`unittest.mock` double configured to return realistic Salesforce response dicts.
"""
from unittest.mock import MagicMock, patch

import pytest


def _query_sf(*query_results):
    """SF double whose successive .query()/.query_all() calls return the given dicts.

    Pass a single dict to make every call return it; pass several to return
    them in order.
    """
    sf = MagicMock()
    if len(query_results) == 1:
        sf.query.return_value = query_results[0]
        sf.query_all.return_value = query_results[0]
    else:
        sf.query.side_effect = list(query_results)
        sf.query_all.side_effect = list(query_results)
    return sf


def _restful_sf(records):
    """SF double whose Tooling-API .restful() call returns the given records."""
    sf = MagicMock()
    sf.restful.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


# ── get_scheduled_jobs ─────────────────────────────────────────────────────────

_CRON_ROWS = [
    {'Id': '08e000000000001', 'State': 'WAITING', 'NextFireTime': '2026-06-01T06:00:00.000+0000',
     'PreviousFireTime': None, 'StartTime': '2026-05-01T06:00:00.000+0000',
     'TimesTriggered': 12, 'CronExpression': '0 0 6 * * ?',
     'CronJobDetail': {'Name': 'Daily Readiness', 'JobType': '7'}},
    {'Id': '08e000000000002', 'State': 'PAUSED', 'NextFireTime': '2026-06-02T06:00:00.000+0000',
     'PreviousFireTime': '2026-05-02T06:00:00.000+0000', 'StartTime': '2026-05-01T06:00:00.000+0000',
     'TimesTriggered': 3, 'CronExpression': '0 0 7 * * ?',
     'CronJobDetail': {'Name': 'Weekly Export', 'JobType': '3'}},
    {'Id': '08e000000000003', 'State': 'ERROR', 'NextFireTime': None,
     'PreviousFireTime': '2026-05-03T06:00:00.000+0000', 'StartTime': '2026-05-01T06:00:00.000+0000',
     'TimesTriggered': 0, 'CronExpression': '0 0 8 * * ?',
     'CronJobDetail': {'Name': 'Broken Job', 'JobType': '7'}},
]


def test_get_scheduled_jobs_returns_list():
    from services.admin_service import get_scheduled_jobs
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _CRON_ROWS})):
        result = get_scheduled_jobs('dev')
    assert isinstance(result, list)
    assert len(result) == 3


def test_get_scheduled_jobs_fields():
    from services.admin_service import get_scheduled_jobs
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _CRON_ROWS})):
        jobs = get_scheduled_jobs('dev')
    job = jobs[0]
    for key in ('id', 'name', 'state', 'state_label', 'job_type_label',
                'next_fire_time', 'cron_expression', 'times_triggered'):
        assert key in job


def test_get_scheduled_jobs_state_labels():
    from services.admin_service import get_scheduled_jobs
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _CRON_ROWS})):
        jobs = get_scheduled_jobs('dev')
    states = {j['state'] for j in jobs}
    assert states == {'WAITING', 'PAUSED', 'ERROR'}
    by_state = {j['state']: j['state_label'] for j in jobs}
    assert by_state['WAITING'] == 'Waiting'
    assert by_state['ERROR'] == 'Error'


# ── get_test_coverage ──────────────────────────────────────────────────────────

_COVERAGE_ROWS = [
    {'ApexClassOrTriggerId': '01p000000000001', 'NumLinesCovered': 90, 'NumLinesUncovered': 10,
     'ApexClassOrTrigger': {'Name': 'WellCoveredClass'}},          # 90% green
    {'ApexClassOrTriggerId': '01p000000000002', 'NumLinesCovered': 60, 'NumLinesUncovered': 40,
     'ApexClassOrTrigger': {'Name': 'MediumClass'}},               # 60% amber
    {'ApexClassOrTriggerId': '01p000000000003', 'NumLinesCovered': 20, 'NumLinesUncovered': 80,
     'ApexClassOrTrigger': {'Name': 'BadClass'}},                  # 20% red
]


def test_get_test_coverage_returns_dict():
    from services.admin_service import get_test_coverage
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_COVERAGE_ROWS)):
        result = get_test_coverage('dev')
    assert isinstance(result, dict)
    assert 'classes' in result
    assert 'summary' in result


def test_get_test_coverage_pct_range():
    from services.admin_service import get_test_coverage
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_COVERAGE_ROWS)):
        result = get_test_coverage('dev')
    for cls in result['classes']:
        assert 0.0 <= cls['pct'] <= 100.0
        assert cls['status'] in ('green', 'amber', 'red')
    by_name = {c['name']: c for c in result['classes']}
    assert by_name['WellCoveredClass']['status'] == 'green'
    assert by_name['MediumClass']['status'] == 'amber'
    assert by_name['BadClass']['status'] == 'red'


def test_get_test_coverage_summary_fields():
    from services.admin_service import get_test_coverage
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_COVERAGE_ROWS)):
        result = get_test_coverage('dev')
    s = result['summary']
    for key in ('total', 'passing', 'failing', 'below_threshold'):
        assert key in s
    assert s['total'] == len(result['classes']) == 3
    assert s['passing'] == 1
    assert s['failing'] == 1


# ── get_deploy_history ─────────────────────────────────────────────────────────

_DEPLOY_ROWS = [
    {'Id': '0Af000000000001', 'Status': 'Succeeded',
     'StartDate': '2026-05-20T10:00:00.000+0000', 'CompletedDate': '2026-05-20T10:05:00.000+0000',
     'CreatedBy': {'Name': 'Todd Finner'}, 'NumberComponentsTotal': 42,
     'NumberComponentErrors': 0, 'NumberTestsCompleted': 18, 'NumberTestErrors': 0,
     'StateDetail': None},
    {'Id': '0Af000000000002', 'Status': 'Failed',
     'StartDate': '2026-05-21T11:00:00.000+0000', 'CompletedDate': '2026-05-21T11:02:30.000+0000',
     'CreatedBy': {'Name': 'Admin User'}, 'NumberComponentsTotal': 10,
     'NumberComponentErrors': 2, 'NumberTestsCompleted': 5, 'NumberTestErrors': 1,
     'StateDetail': 'Component errors'},
]


def test_get_deploy_history_returns_list():
    from services.admin_service import get_deploy_history
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_DEPLOY_ROWS)):
        result = get_deploy_history('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_deploy_history_fields():
    from services.admin_service import get_deploy_history
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_DEPLOY_ROWS)):
        deploys = get_deploy_history('dev')
    d = deploys[0]
    for key in ('id', 'status', 'start_date', 'created_by', 'duration_seconds',
                'num_components_total', 'num_component_errors',
                'num_tests_completed', 'num_test_errors', 'state_detail'):
        assert key in d


def test_get_deploy_history_duration_computed():
    from services.admin_service import get_deploy_history
    with patch('services.admin_service.get_sf', return_value=_restful_sf(_DEPLOY_ROWS)):
        deploys = get_deploy_history('dev')
    for d in deploys:
        assert d['duration_seconds'] is not None
        assert d['duration_seconds'] >= 0
    # First row spans 5 minutes = 300s.
    assert deploys[0]['duration_seconds'] == 300


# ── get_user_audit ─────────────────────────────────────────────────────────────

_USER_ROWS = [
    {'Id': '005000000000001', 'Name': 'Active Admin', 'Username': 'admin@doane.edu',
     'IsActive': True, 'LastLoginDate': '2026-05-21T08:00:00.000+0000',
     'UserType': 'Standard', 'Profile': {'Name': 'System Administrator'},
     'CreatedDate': '2024-01-01T00:00:00.000+0000'},
    {'Id': '005000000000002', 'Name': 'Stale User', 'Username': 'stale@doane.edu',
     'IsActive': True, 'LastLoginDate': '2025-01-01T08:00:00.000+0000',
     'UserType': 'Standard', 'Profile': {'Name': 'Standard User'},
     'CreatedDate': '2023-01-01T00:00:00.000+0000'},
    {'Id': '005000000000003', 'Name': 'Never Logged In', 'Username': 'new@doane.edu',
     'IsActive': True, 'LastLoginDate': None,
     'UserType': 'Standard', 'Profile': {'Name': 'Standard User'},
     'CreatedDate': '2026-05-01T00:00:00.000+0000'},
    {'Id': '005000000000004', 'Name': 'Disabled User', 'Username': 'old@doane.edu',
     'IsActive': False, 'LastLoginDate': '2025-06-01T08:00:00.000+0000',
     'UserType': 'Standard', 'Profile': {'Name': 'Standard User'},
     'CreatedDate': '2022-01-01T00:00:00.000+0000'},
]


def test_get_user_audit_returns_dict():
    from services.admin_service import get_user_audit
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _USER_ROWS})):
        result = get_user_audit('dev')
    assert isinstance(result, dict)
    assert 'users' in result
    assert 'summary' in result


def test_get_user_audit_summary_fields():
    from services.admin_service import get_user_audit
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _USER_ROWS})):
        result = get_user_audit('dev')
    s = result['summary']
    for key in ('total_active', 'inactive_90d', 'never_logged_in', 'sysadmins'):
        assert key in s
    # 3 active users, 1 sysadmin, 1 never logged in, 1 stale (>90d).
    assert s['total_active'] == 3
    assert s['sysadmins'] == 1
    assert s['never_logged_in'] == 1
    assert s['inactive_90d'] == 1


def test_get_user_audit_flags():
    from services.admin_service import get_user_audit
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _USER_ROWS})):
        result = get_user_audit('dev')
    flags = {u['flag'] for u in result['users'] if u['flag'] is not None}
    assert {'inactive', 'never_logged_in', 'inactive_90d'} <= flags


def test_get_user_audit_user_fields():
    from services.admin_service import get_user_audit
    with patch('services.admin_service.get_sf', return_value=_query_sf({'records': _USER_ROWS})):
        result = get_user_audit('dev')
    u = result['users'][0]
    for key in ('id', 'name', 'username', 'is_active', 'last_login_date',
                'profile_name', 'flag'):
        assert key in u
