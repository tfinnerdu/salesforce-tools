"""Tests for services.readiness_validator."""
import pytest
from unittest.mock import patch


def test_check_sis_id_coverage_returns_dict(mock_sf):
    from services.readiness_validator import check_sis_id_coverage
    result = check_sis_id_coverage(mock_sf)
    assert isinstance(result, dict)
    assert 'pct' in result
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')
    assert 0 <= result['pct'] <= 100


def test_check_sis_id_coverage_correct_numbers(mock_sf):
    from services.readiness_validator import check_sis_id_coverage
    result = check_sis_id_coverage(mock_sf)
    # mock has 4312 total, 3065 covered = ~71%
    assert result['total'] == 4312
    assert result['status'] == 'red'  # 71% < 90%


def test_check_ethos_guid_coverage_amber(mock_sf):
    from services.readiness_validator import check_ethos_guid_coverage
    result = check_ethos_guid_coverage(mock_sf)
    assert result['total'] == 4312
    # 3923 covered = 91% -> amber
    assert result['status'] in ('amber', 'green')


def test_check_contactpoint_parents_returns_broken_count(mock_sf):
    from services.readiness_validator import check_contactpoint_parents
    result = check_contactpoint_parents(mock_sf)
    assert 'broken_count' in result or 'covered' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_check_required_fields_returns_issues(mock_sf):
    from services.readiness_validator import check_required_fields
    result = check_required_fields(mock_sf)
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_check_duplicates_returns_status(mock_sf):
    from services.readiness_validator import check_duplicates
    result = check_duplicates(mock_sf)
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_check_individual_links_returns_status(mock_sf):
    from services.readiness_validator import check_individual_links
    result = check_individual_links(mock_sf)
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_run_full_readiness_check_structure():
    from services.readiness_validator import run_full_readiness_check
    result = run_full_readiness_check('dev')
    assert 'checks' in result
    assert 'overall_pct' in result
    assert 'overall_status' in result
    assert 'run_at' in result
    assert isinstance(result['checks'], list)
    assert len(result['checks']) >= 5
    assert 0 <= result['overall_pct'] <= 100
    assert result['overall_status'] in ('green', 'amber', 'red')


def test_run_full_readiness_check_each_check_has_required_keys():
    from services.readiness_validator import run_full_readiness_check
    result = run_full_readiness_check('dev')
    required_keys = {'name', 'status', 'pct'}
    for check in result['checks']:
        assert required_keys.issubset(check.keys()), f"Check missing keys: {check}"


def test_save_run_handles_db_error():
    """save_run should not crash when DB is unavailable."""
    from services.readiness_validator import save_run
    result = {'checks': [], 'overall_pct': 75.0, 'overall_status': 'red', 'run_at': '2026-01-01T00:00:00'}
    # No DB configured — should log and return, not raise
    save_run('dev', result)


def test_get_history_returns_list_without_db():
    from services.readiness_validator import get_history
    # With no DB, should return empty list (not crash)
    result = get_history('dev', limit=5)
    assert isinstance(result, list)


def test_overall_status_is_red_when_any_check_red(mock_sf):
    from services.readiness_validator import run_full_readiness_check
    result = run_full_readiness_check('dev')
    red_checks = [c for c in result['checks'] if c['status'] == 'red']
    if red_checks:
        assert result['overall_status'] == 'red'
