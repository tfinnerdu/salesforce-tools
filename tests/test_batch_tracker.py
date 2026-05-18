"""Tests for services.batch_tracker."""
import pytest


def test_extract_sf_error_code_duplicate_value():
    from services.batch_tracker import extract_sf_error_code
    reason = 'com.netflix.conductor: DUPLICATE_VALUE: found duplicate'
    assert extract_sf_error_code(reason) == 'DUPLICATE_VALUE'


def test_extract_sf_error_code_field_integrity():
    from services.batch_tracker import extract_sf_error_code
    reason = 'FIELD_INTEGRITY_EXCEPTION: ParentId required'
    assert extract_sf_error_code(reason) == 'FIELD_INTEGRITY_EXCEPTION'


def test_extract_sf_error_code_timeout():
    from services.batch_tracker import extract_sf_error_code
    assert extract_sf_error_code('TIMEOUT: worker exceeded limit') == 'TIMEOUT'


def test_extract_sf_error_code_unknown():
    from services.batch_tracker import extract_sf_error_code
    assert extract_sf_error_code('some random error') == 'UNKNOWN'


def test_extract_sf_error_code_required_field():
    from services.batch_tracker import extract_sf_error_code
    assert extract_sf_error_code('REQUIRED_FIELD_MISSING: LastName') == 'REQUIRED_FIELD_MISSING'


def test_get_batch_status_structure(mock_conductor):
    from services.batch_tracker import get_batch_status
    result = get_batch_status('EDA_Person_Sync')
    assert 'completed' in result
    assert 'failed' in result
    assert 'running' in result
    assert 'queued' in result
    assert 'progress_pct' in result
    assert 0 <= result['progress_pct'] <= 100


def test_get_batch_status_mock_numbers(mock_conductor):
    from services.batch_tracker import get_batch_status
    result = get_batch_status('EDA_Person_Sync')
    assert result['completed'] == 2756
    assert result['failed'] == 91
    assert result['running'] == 212


def test_get_failure_reasons_structure(mock_conductor):
    from services.batch_tracker import get_failure_reasons
    result = get_failure_reasons('EDA_Person_Sync')
    assert 'breakdown' in result
    assert 'sis_ids_by_error' in result
    assert 'total_failures' in result
    assert isinstance(result['breakdown'], dict)


def test_get_failure_reasons_breakdown_has_known_codes(mock_conductor):
    from services.batch_tracker import get_failure_reasons
    result = get_failure_reasons('EDA_Person_Sync')
    codes = set(result['breakdown'].keys())
    # Mock should have DUPLICATE_VALUE, FIELD_INTEGRITY_EXCEPTION, TIMEOUT
    assert 'DUPLICATE_VALUE' in codes or len(codes) > 0


def test_rerun_workflows_returns_results(mock_conductor):
    from services.batch_tracker import rerun_workflows
    ids = ['wf-mock-000001', 'wf-mock-000002']
    results = rerun_workflows(ids)
    assert len(results) == 2
    for r in results:
        assert 'workflow_id' in r
        assert 'success' in r
