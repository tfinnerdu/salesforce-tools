"""Tests for services.batch_tracker."""
from unittest.mock import MagicMock, patch

import pytest


def _fake_conductor(batch_status=None, workflows=None, retry_resp=None):
    """A Conductor double configured for batch_tracker's call sites."""
    c = MagicMock()
    c.get_batch_status.return_value = batch_status or {}
    c.search_workflows.return_value = workflows or []
    c.retry_workflow.return_value = retry_resp or {'status_code': 200}
    return c


_BATCH_STATUS = {
    'total': 3000,
    'completed': 2700,
    'failed': 90,
    'running': 200,
    'queued': 10,
    'timed_out': 0,
}

_FAILED_WORKFLOWS = [
    {'workflowId': 'wf-1', 'status': 'FAILED',
     'reasonForIncompletion': 'DUPLICATE_VALUE: found duplicate',
     'input': '{"sisId": "STU001"}'},
    {'workflowId': 'wf-2', 'status': 'FAILED',
     'reasonForIncompletion': 'DUPLICATE_VALUE: found duplicate',
     'input': '{"sisId": "STU002"}'},
    {'workflowId': 'wf-3', 'status': 'FAILED',
     'reasonForIncompletion': 'FIELD_INTEGRITY_EXCEPTION: ParentId required',
     'input': '{"sisId": "STU003"}'},
    {'workflowId': 'wf-4', 'status': 'FAILED',
     'reasonForIncompletion': 'TIMEOUT: worker exceeded limit',
     'input': '{"sisId": "STU004"}'},
]


# ── extract_sf_error_code (pure logic, unchanged) ─────────────────────────────

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


# ── get_batch_status ──────────────────────────────────────────────────────────

def test_get_batch_status_structure():
    from services.batch_tracker import get_batch_status
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(batch_status=_BATCH_STATUS)):
        result = get_batch_status('EDA_Person_Sync')
    assert 'completed' in result
    assert 'failed' in result
    assert 'running' in result
    assert 'queued' in result
    assert 'progress_pct' in result
    assert 0 <= result['progress_pct'] <= 100


def test_get_batch_status_passes_through_conductor_counts():
    from services.batch_tracker import get_batch_status
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(batch_status=_BATCH_STATUS)):
        result = get_batch_status('EDA_Person_Sync')
    assert result['completed'] == 2700
    assert result['failed'] == 90
    assert result['running'] == 200


def test_get_batch_status_progress_pct_computed():
    from services.batch_tracker import get_batch_status
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(batch_status=_BATCH_STATUS)):
        result = get_batch_status('EDA_Person_Sync')
    # (completed + failed) / total = (2700 + 90) / 3000 = 93.0
    assert result['progress_pct'] == 93.0


def test_get_batch_status_rate_and_eta_are_none():
    """The fabricated 48/min rate was removed — both are always None now."""
    from services.batch_tracker import get_batch_status
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(batch_status=_BATCH_STATUS)):
        result = get_batch_status('EDA_Person_Sync')
    assert result['rate_per_min'] is None
    assert result['eta_minutes'] is None


# ── get_failure_reasons ───────────────────────────────────────────────────────

def test_get_failure_reasons_structure():
    from services.batch_tracker import get_failure_reasons
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = get_failure_reasons('EDA_Person_Sync')
    assert 'breakdown' in result
    assert 'sis_ids_by_error' in result
    assert 'total_failures' in result
    assert isinstance(result['breakdown'], dict)
    assert result['total_failures'] == 4


def test_get_failure_reasons_breakdown_has_known_codes():
    from services.batch_tracker import get_failure_reasons
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = get_failure_reasons('EDA_Person_Sync')
    codes = set(result['breakdown'].keys())
    assert 'DUPLICATE_VALUE' in codes
    assert result['breakdown']['DUPLICATE_VALUE'] == 2
    assert result['breakdown']['FIELD_INTEGRITY_EXCEPTION'] == 1
    assert result['breakdown']['TIMEOUT'] == 1


def test_get_failure_reasons_sis_ids_extracted_from_input():
    from services.batch_tracker import get_failure_reasons
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = get_failure_reasons('EDA_Person_Sync')
    assert sorted(result['sis_ids_by_error']['DUPLICATE_VALUE']) == ['STU001', 'STU002']


# ── rerun_workflows ───────────────────────────────────────────────────────────

def test_rerun_workflows_returns_results():
    from services.batch_tracker import rerun_workflows
    ids = ['wf-1', 'wf-2']
    with patch('services.batch_tracker.get_conductor_client',
               return_value=_fake_conductor(retry_resp={'workflow_id': 'x', 'status_code': 200})):
        results = rerun_workflows(ids)
    assert len(results) == 2
    for r in results:
        assert 'workflow_id' in r
        assert 'success' in r
        assert r['success'] is True
