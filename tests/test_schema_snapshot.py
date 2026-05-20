"""Tests for services.schema_snapshot and /schema/snapshots routes."""
import json
import pytest


# ── Service tests ─────────────────────────────────────────────────────────────

def test_take_snapshot_returns_expected_keys():
    from services import schema_snapshot
    result = schema_snapshot.take_snapshot(org='dev', sobject='Account')
    assert 'id' in result
    assert 'org' in result
    assert 'sobject' in result
    assert 'label' in result
    assert 'field_count' in result


def test_take_snapshot_mock_account_includes_sis_id():
    from services import schema_snapshot
    result = schema_snapshot.take_snapshot(org='dev', sobject='Account')
    # In mock mode, field_count should include SIS_ID__c and Ethos_Guid__c
    assert result['field_count'] >= 5
    assert result['sobject'] == 'Account'
    assert result['org'] == 'dev'


def test_list_snapshots_returns_list():
    from services import schema_snapshot
    result = schema_snapshot.list_snapshots()
    assert isinstance(result, list)


def test_diff_snapshots_mock_returns_required_keys():
    from services import schema_snapshot
    result = schema_snapshot.diff_snapshots(1, 2)
    assert 'added' in result
    assert 'removed' in result
    assert 'changed' in result
    assert 'summary' in result


def test_diff_snapshots_summary_has_integer_counts():
    from services import schema_snapshot
    result = schema_snapshot.diff_snapshots(1, 2)
    summary = result['summary']
    assert isinstance(summary.get('added'), int)
    assert isinstance(summary.get('removed'), int)
    assert isinstance(summary.get('changed'), int)


def test_mock_diff_has_sobject_key():
    from services.schema_snapshot import _mock_diff
    result = _mock_diff()
    assert 'sobject' in result
    assert result['sobject'] == 'Account'


def test_mock_fields_account_includes_sis_id():
    from services.schema_snapshot import _mock_fields
    fields = _mock_fields('Account')
    names = [f['name'] for f in fields]
    assert 'SIS_ID__c' in names


def test_mock_fields_contact_has_at_least_three_base_fields():
    from services.schema_snapshot import _mock_fields
    fields = _mock_fields('Contact')
    assert len(fields) >= 3
    names = [f['name'] for f in fields]
    assert 'Id' in names
    assert 'Name' in names
    assert 'CreatedDate' in names


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_snapshots_list_returns_200_and_success(client):
    resp = client.get('/schema/snapshots/list')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_post_snapshots_take_returns_200_and_sobject_in_data(session_client):
    resp = session_client.post(
        '/schema/snapshots/take',
        data=json.dumps({'sobject': 'Account'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['sobject'] == 'Account'
