"""Tests for services.error_reconciler."""
from unittest.mock import MagicMock, patch

import pytest


def _fake_conductor(workflows=None, retry_resp=None):
    """A Conductor double configured for error_reconciler's call sites."""
    c = MagicMock()
    c.search_workflows.return_value = workflows or []
    c.retry_workflow.return_value = retry_resp or {'status_code': 200}
    return c


def _wf(wf_id, reason, sis_id):
    return {
        'workflowId': wf_id,
        'status': 'FAILED',
        'reasonForIncompletion': reason,
        'input': f'{{"sisId": "{sis_id}"}}',
    }


# A failure set: 3 DUPLICATE_VALUE (high), 2 INVALID_FIELD (medium), 1 TIMEOUT (low).
_FAILED_WORKFLOWS = [
    _wf('wf-1', 'DUPLICATE_VALUE: dup external id', 'STU001'),
    _wf('wf-2', 'DUPLICATE_VALUE: dup external id', 'STU002'),
    _wf('wf-3', 'DUPLICATE_VALUE: dup external id', 'STU003'),
    _wf('wf-4', 'INVALID_FIELD: bad api name', 'STU004'),
    _wf('wf-5', 'INVALID_FIELD: bad api name', 'STU005'),
    _wf('wf-6', 'TIMEOUT: worker exceeded limit', 'STU006'),
]


def test_categorize_returns_list():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync', hours_back=24)
    assert isinstance(result, list)


def test_categorize_has_required_keys():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync', hours_back=24)
    assert len(result) > 0
    required = {'error_code', 'count', 'sis_ids', 'workflow_ids', 'cause', 'suggested_fix', 'severity'}
    for cat in result:
        assert required.issubset(cat.keys()), f"Category missing keys: {cat}"


def test_categorize_sorted_by_count_desc():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync')
    counts = [c['count'] for c in result]
    assert counts == sorted(counts, reverse=True)


def test_categorize_severity_values():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync')
    valid = {'high', 'medium', 'low'}
    for cat in result:
        assert cat['severity'] in valid


def test_categorize_duplicate_value_is_high_severity():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync')
    dup = next((c for c in result if c['error_code'] == 'DUPLICATE_VALUE'), None)
    assert dup is not None
    assert dup['severity'] == 'high'
    assert dup['count'] == 3


def test_categorize_timeout_is_low_severity():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync')
    timeout = next((c for c in result if c['error_code'] == 'TIMEOUT'), None)
    assert timeout is not None
    assert timeout['severity'] == 'low'
    assert timeout['count'] == 1


def test_categorize_collects_sis_and_workflow_ids():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=_FAILED_WORKFLOWS)):
        result = categorize_conductor_failures('EDA_Person_Sync')
    dup = next(c for c in result if c['error_code'] == 'DUPLICATE_VALUE')
    assert sorted(dup['sis_ids']) == ['STU001', 'STU002', 'STU003']
    assert sorted(dup['workflow_ids']) == ['wf-1', 'wf-2', 'wf-3']


def test_categorize_empty_when_no_failures():
    from services.error_reconciler import categorize_conductor_failures
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(workflows=[])):
        result = categorize_conductor_failures('EDA_Person_Sync')
    assert result == []


def test_rerun_workflows_returns_list():
    from services.error_reconciler import rerun_workflows
    with patch('services.error_reconciler.get_conductor_client',
               return_value=_fake_conductor(retry_resp={'workflow_id': 'x', 'status_code': 200})):
        result = rerun_workflows(['wf-001', 'wf-002'])
    assert len(result) == 2
    for r in result:
        assert 'workflow_id' in r
        assert r['success'] is True
