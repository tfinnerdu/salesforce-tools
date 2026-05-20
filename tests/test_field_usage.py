"""Tests for services.field_usage and /schema/field-usage routes."""
import json
import pytest


# ── Service tests ─────────────────────────────────────────────────────────────

def test_run_returns_top_level_keys():
    from services import field_usage
    result = field_usage.run(org='dev', sobject='Account')
    assert 'sobject' in result
    assert 'total_records' in result
    assert 'fields' in result


def test_fields_is_a_list():
    from services import field_usage
    result = field_usage.run(org='dev', sobject='Account')
    assert isinstance(result['fields'], list)


def test_each_field_has_required_keys():
    from services import field_usage
    result = field_usage.run(org='dev', sobject='Account')
    for f in result['fields']:
        assert 'name' in f
        assert 'label' in f
        assert 'pct' in f
        assert 'status' in f


def test_status_green_when_pct_gte_75():
    from services.field_usage import _status
    assert _status(75.0) == 'green'
    assert _status(99.5) == 'green'
    assert _status(100.0) == 'green'


def test_status_red_when_pct_lt_25():
    from services.field_usage import _status
    assert _status(24.9) == 'red'
    assert _status(10.0) == 'red'
    assert _status(0.1) == 'red'


def test_status_empty_when_pct_zero():
    from services.field_usage import _status
    assert _status(0.0) == 'empty'


def test_per_field_exception_sets_status_skip(monkeypatch):
    """When a field's COUNT query raises, status should be 'skip'."""
    from services import field_usage
    from sf_provider import MockSalesforce

    original_query = MockSalesforce.query

    call_count = {'n': 0}

    def patched_query(self, soql):
        call_count['n'] += 1
        # First call (total count) succeeds; subsequent calls (per-field) raise
        if call_count['n'] == 1:
            return {'totalSize': 100, 'done': True, 'records': []}
        raise Exception('field not filterable')

    monkeypatch.setattr(MockSalesforce, 'query', patched_query)
    result = field_usage.run(org='dev', sobject='Account')
    skip_fields = [f for f in result['fields'] if f['status'] == 'skip']
    assert len(skip_fields) > 0


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_field_usage_page_returns_200(client):
    resp = client.get('/schema/field-usage')
    assert resp.status_code == 200


def test_post_field_usage_run_with_sobject_returns_200_success(session_client):
    resp = session_client.post(
        '/schema/field-usage/run',
        data=json.dumps({'sobject': 'Account'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'fields' in data['data']


def test_post_field_usage_run_without_sobject_returns_400(client):
    resp = client.post(
        '/schema/field-usage/run',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'sobject required' in data['error']
