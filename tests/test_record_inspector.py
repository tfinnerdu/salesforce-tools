"""Tests for services.record_inspector — single-record field browser."""
import pytest
from services import record_inspector


# ── _mock_record ───────────────────────────────────────────────────────────────

def test_mock_record_returns_expected_shape():
    result = record_inspector._mock_record('Account', 'AAA001')
    assert result['object'] == 'Account'
    assert result['record_id'] == 'AAA001'
    assert result['mock'] is True
    assert isinstance(result['fields'], list)
    assert len(result['fields']) > 0
    names = [f['name'] for f in result['fields']]
    assert 'Id' in names
    assert 'SIS_ID__c' in names
    assert 'Ethos_Guid__c' in names


def test_mock_record_each_field_has_required_keys():
    result = record_inspector._mock_record('Account', 'X')
    for f in result['fields']:
        assert 'name' in f
        assert 'label' in f
        assert 'type' in f
        assert 'value' in f


def test_mock_record_total_fields_matches_list():
    result = record_inspector._mock_record('Account', 'X')
    assert result['total_fields'] == len(result['fields'])


# ── get_record — mock mode (SF_MOCK=true by default in tests) ─────────────────

def test_get_record_mock_returns_dict_with_fields():
    result = record_inspector.get_record('dev', 'Account', 'TEST001')
    assert result['object'] == 'Account'
    assert result['record_id'] == 'TEST001'
    assert 'fields' in result
    assert result['total_fields'] > 0


def test_get_record_mock_external_id_includes_lookup_mode():
    result = record_inspector.get_record('dev', 'Account', '12345', external_id_field='SIS_ID__c')
    assert result['lookup_mode'] == 'external_id:SIS_ID__c'


def test_get_record_mock_sf_id_has_sf_id_lookup_mode():
    result = record_inspector.get_record('dev', 'Account', 'TEST001')
    # mock always returns; lookup_mode set only when external_id_field given
    assert 'lookup_mode' not in result or result.get('lookup_mode') != 'external_id:SIS_ID__c'


def test_get_record_raises_on_missing_object():
    with pytest.raises(ValueError, match='object_name and record_id are required'):
        record_inspector.get_record('dev', '', 'TEST001')


def test_get_record_raises_on_missing_record_id():
    with pytest.raises(ValueError, match='object_name and record_id are required'):
        record_inspector.get_record('dev', 'Account', '')


# ── Routes ────────────────────────────────────────────────────────────────────

def test_record_inspector_page_renders(client):
    resp = client.get('/schema/inspect')
    assert resp.status_code == 200
    assert b'Record Inspector' in resp.data


def test_record_inspector_page_has_sub_nav(client):
    resp = client.get('/schema/inspect')
    assert b'/schema/crosswalk' in resp.data
    assert b'/schema/org-diff' in resp.data
    assert b'/schema/snapshots' in resp.data
    assert b'/schema/inspect' in resp.data


def test_inspect_run_returns_fields(client):
    resp = client.post('/schema/inspect/run',
                       json={'object': 'Account', 'record_id': 'TEST001'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'fields' in body['data']
    assert body['data']['total_fields'] > 0


def test_inspect_run_external_id(client):
    resp = client.post('/schema/inspect/run',
                       json={'object': 'Account', 'record_id': '12345',
                             'external_id_field': 'SIS_ID__c'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['lookup_mode'] == 'external_id:SIS_ID__c'


def test_inspect_run_missing_object_returns_400(client):
    resp = client.post('/schema/inspect/run',
                       json={'record_id': 'TEST001'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_inspect_run_missing_record_id_returns_400(client):
    resp = client.post('/schema/inspect/run',
                       json={'object': 'Account'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_inspect_run_service_error_returns_500(client, monkeypatch):
    import services.record_inspector as ri
    monkeypatch.setattr(ri, 'get_record',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/schema/inspect/run',
                       json={'object': 'Account', 'record_id': 'X'})
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
