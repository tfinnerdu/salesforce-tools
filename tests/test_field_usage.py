"""Tests for services.field_usage and /schema/field-usage routes."""
import json
from unittest.mock import MagicMock, patch

import pytest


# A describe payload — field_usage.get_field_list reads name/label/type/queryable.
_ACCOUNT_DESCRIBE = {
    'name': 'Account',
    'fields': [
        {'name': 'Id', 'label': 'Account ID', 'type': 'id', 'queryable': True},
        {'name': 'Name', 'label': 'Account Name', 'type': 'string', 'queryable': True},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string', 'queryable': True},
        {'name': 'Ethos_Guid__c', 'label': 'Ethos GUID', 'type': 'string', 'queryable': True},
        {'name': 'PersonEmail', 'label': 'Email', 'type': 'email', 'queryable': True},
    ],
}


def _fake_sf(describe=None, total=100, populated=80, raise_per_field=False):
    """A Salesforce double for field_usage.

    ``sf.restful`` returns the describe; ``sf.query`` returns COUNT() results —
    the first call (total count, no WHERE) returns ``total``; subsequent
    per-field calls return ``populated`` (or raise when ``raise_per_field``).
    """
    sf = MagicMock()
    sf.restful.return_value = describe if describe is not None else _ACCOUNT_DESCRIBE

    def query(soql):
        if 'WHERE' not in soql:
            return {'totalSize': total, 'done': True, 'records': []}
        if raise_per_field:
            raise Exception('field not filterable')
        return {'totalSize': populated, 'done': True, 'records': []}

    sf.query.side_effect = query
    return sf


# ── Service tests ─────────────────────────────────────────────────────────────

def test_run_returns_top_level_keys():
    with patch('services.field_usage.get_sf', return_value=_fake_sf()):
        from services import field_usage
        result = field_usage.run(org='dev', sobject='Account')
    assert 'sobject' in result
    assert 'total_records' in result
    assert 'fields' in result


def test_fields_is_a_list():
    with patch('services.field_usage.get_sf', return_value=_fake_sf()):
        from services import field_usage
        result = field_usage.run(org='dev', sobject='Account')
    assert isinstance(result['fields'], list)
    assert len(result['fields']) > 0


def test_each_field_has_required_keys():
    with patch('services.field_usage.get_sf', return_value=_fake_sf()):
        from services import field_usage
        result = field_usage.run(org='dev', sobject='Account')
    for f in result['fields']:
        assert 'name' in f
        assert 'label' in f
        assert 'pct' in f
        assert 'status' in f


def test_run_computes_fill_percentage():
    """pct = populated / total * 100 for each filterable field."""
    with patch('services.field_usage.get_sf',
               return_value=_fake_sf(total=200, populated=150)):
        from services import field_usage
        result = field_usage.run(org='dev', sobject='Account')
    assert result['total_records'] == 200
    # 150 / 200 = 75% → green
    for f in result['fields']:
        assert f['pct'] == 75.0
        assert f['status'] == 'green'


# ── _status (pure logic) ──────────────────────────────────────────────────────

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


def test_per_field_exception_sets_status_skip():
    """When a field's COUNT query raises, that field's status is 'skip'."""
    with patch('services.field_usage.get_sf',
               return_value=_fake_sf(raise_per_field=True)):
        from services import field_usage
        result = field_usage.run(org='dev', sobject='Account')
    skip_fields = [f for f in result['fields'] if f['status'] == 'skip']
    assert len(skip_fields) > 0
    # Every field's per-field query raised, so all are skipped.
    assert len(skip_fields) == len(result['fields'])
    for f in skip_fields:
        assert f['pct'] is None
        assert f['populated'] is None


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_field_usage_page_returns_200(client):
    resp = client.get('/schema/field-usage')
    assert resp.status_code == 200


def test_post_field_usage_run_with_sobject_returns_200_success(session_client):
    with patch('services.field_usage.get_sf', return_value=_fake_sf()):
        resp = session_client.post(
            '/api/v1/schema/field-usage/run',
            data=json.dumps({'sobject': 'Account'}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'fields' in data['data']


def test_post_field_usage_run_without_sobject_returns_400(client):
    resp = client.post(
        '/api/v1/schema/field-usage/run',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'sobject required' in data['error']
