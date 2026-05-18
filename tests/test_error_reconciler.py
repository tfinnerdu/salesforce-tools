"""Tests for services.error_reconciler."""
import pytest


def test_categorize_returns_list():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync', hours_back=24)
    assert isinstance(result, list)


def test_categorize_has_required_keys():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync', hours_back=24)
    assert len(result) > 0
    required = {'error_code', 'count', 'sis_ids', 'workflow_ids', 'cause', 'suggested_fix', 'severity'}
    for cat in result:
        assert required.issubset(cat.keys()), f"Category missing keys: {cat}"


def test_categorize_sorted_by_count_desc():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync')
    counts = [c['count'] for c in result]
    assert counts == sorted(counts, reverse=True)


def test_categorize_severity_values():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync')
    valid = {'high', 'medium', 'low'}
    for cat in result:
        assert cat['severity'] in valid


def test_categorize_duplicate_value_is_high_severity():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync')
    dup = next((c for c in result if c['error_code'] == 'DUPLICATE_VALUE'), None)
    if dup:
        assert dup['severity'] == 'high'
        assert dup['count'] == 44


def test_categorize_timeout_is_low_severity():
    from services.error_reconciler import categorize_conductor_failures
    result = categorize_conductor_failures('EDA_Person_Sync')
    timeout = next((c for c in result if c['error_code'] == 'TIMEOUT'), None)
    if timeout:
        assert timeout['severity'] == 'low'
        assert timeout['count'] == 16


def test_rerun_workflows_returns_list():
    from services.error_reconciler import rerun_workflows
    result = rerun_workflows(['wf-001', 'wf-002'])
    assert len(result) == 2
    for r in result:
        assert 'workflow_id' in r
