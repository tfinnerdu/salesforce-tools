"""Tests for services.admin_service."""
import pytest


def test_get_scheduled_jobs_returns_list(mock_sf):
    from services.admin_service import get_scheduled_jobs
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_scheduled_jobs('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_scheduled_jobs_fields(mock_sf):
    from services.admin_service import get_scheduled_jobs
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        jobs = get_scheduled_jobs('dev')
    job = jobs[0]
    assert 'id' in job
    assert 'name' in job
    assert 'state' in job
    assert 'state_label' in job
    assert 'job_type_label' in job
    assert 'next_fire_time' in job
    assert 'cron_expression' in job
    assert 'times_triggered' in job


def test_get_scheduled_jobs_state_labels(mock_sf):
    from services.admin_service import get_scheduled_jobs
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        jobs = get_scheduled_jobs('dev')
    states = {j['state'] for j in jobs}
    # mock produces WAITING, PAUSED, ERROR
    assert states & {'WAITING', 'PAUSED', 'ERROR'}


def test_get_test_coverage_returns_dict(mock_sf):
    from services.admin_service import get_test_coverage
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_test_coverage('dev')
    assert isinstance(result, dict)
    assert 'classes' in result
    assert 'summary' in result


def test_get_test_coverage_pct_range(mock_sf):
    from services.admin_service import get_test_coverage
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_test_coverage('dev')
    for cls in result['classes']:
        assert 0.0 <= cls['pct'] <= 100.0
        assert cls['status'] in ('green', 'amber', 'red')


def test_get_test_coverage_summary_fields(mock_sf):
    from services.admin_service import get_test_coverage
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_test_coverage('dev')
    s = result['summary']
    assert 'total' in s
    assert 'passing' in s
    assert 'failing' in s
    assert 'below_threshold' in s
    assert s['total'] == len(result['classes'])


def test_get_deploy_history_returns_list(mock_sf):
    from services.admin_service import get_deploy_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_deploy_history('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_deploy_history_fields(mock_sf):
    from services.admin_service import get_deploy_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        deploys = get_deploy_history('dev')
    d = deploys[0]
    assert 'id' in d
    assert 'status' in d
    assert 'start_date' in d
    assert 'created_by' in d
    assert 'duration_seconds' in d
    assert 'num_components_total' in d
    assert 'num_component_errors' in d
    assert 'num_tests_completed' in d
    assert 'num_test_errors' in d
    assert 'state_detail' in d


def test_get_deploy_history_duration_computed(mock_sf):
    from services.admin_service import get_deploy_history
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        deploys = get_deploy_history('dev')
    # All mock records have both StartDate and CompletedDate so duration should be set
    for d in deploys:
        assert d['duration_seconds'] is not None
        assert d['duration_seconds'] >= 0


def test_get_user_audit_returns_dict(mock_sf):
    from services.admin_service import get_user_audit
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_user_audit('dev')
    assert isinstance(result, dict)
    assert 'users' in result
    assert 'summary' in result


def test_get_user_audit_summary_fields(mock_sf):
    from services.admin_service import get_user_audit
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_user_audit('dev')
    s = result['summary']
    assert 'total_active' in s
    assert 'inactive_90d' in s
    assert 'never_logged_in' in s
    assert 'sysadmins' in s


def test_get_user_audit_flags(mock_sf):
    from services.admin_service import get_user_audit
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_user_audit('dev')
    flags = {u['flag'] for u in result['users'] if u['flag'] is not None}
    # mock has inactive accounts (idx % 8 == 0) and never-logged-in (days_ago=None)
    assert 'inactive' in flags or 'never_logged_in' in flags


def test_get_user_audit_user_fields(mock_sf):
    from services.admin_service import get_user_audit
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_user_audit('dev')
    u = result['users'][0]
    assert 'id' in u
    assert 'name' in u
    assert 'username' in u
    assert 'is_active' in u
    assert 'last_login_date' in u
    assert 'profile_name' in u
    assert 'flag' in u
