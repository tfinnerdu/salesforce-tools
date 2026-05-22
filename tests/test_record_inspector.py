"""Tests for services.record_inspector — single-record field browser."""
import pytest
from unittest.mock import patch

from services import record_inspector


# ── Stub Salesforce client ────────────────────────────────────────────────────

_DESCRIBE = {
    'name': 'Account',
    'fields': [
        {'name': 'Id', 'label': 'Record ID', 'type': 'id'},
        {'name': 'Name', 'label': 'Account Name', 'type': 'string'},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string'},
        {'name': 'Ethos_Guid__c', 'label': 'Ethos GUID', 'type': 'string'},
        {'name': 'BillingAddress', 'label': 'Billing Address', 'type': 'address'},
    ],
}

_RECORD = {
    'Id': 'TEST001',
    'Name': 'Jane Doe',
    'SIS_ID__c': '12345',
    'Ethos_Guid__c': 'abc-guid',
}


class _StubSF:
    """SF double serving an object describe and a single-record fetch via restful."""
    def __init__(self, describe=None, record=None):
        self._describe = describe if describe is not None else _DESCRIBE
        self._record = record if record is not None else _RECORD

    def restful(self, path, params=None):
        if path.endswith('/describe'):
            return self._describe
        # record-fetch path: sobjects/Account/<id> or sobjects/Account/<extid>/<val>
        return dict(self._record)


def _patch_sf(stub):
    return patch('services.record_inspector.get_sf', return_value=stub)


# ── get_record — happy path ───────────────────────────────────────────────────

def test_get_record_returns_dict_with_fields():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    assert result['object'] == 'Account'
    assert result['record_id'] == 'TEST001'
    assert 'fields' in result
    assert result['total_fields'] > 0


def test_get_record_skips_compound_fields():
    """Compound types (address/location/base64) are excluded from the field list."""
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    names = [f['name'] for f in result['fields']]
    assert 'Id' in names
    assert 'SIS_ID__c' in names
    assert 'Ethos_Guid__c' in names
    assert 'BillingAddress' not in names  # 'address' type skipped


def test_get_record_each_field_has_required_keys():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    for f in result['fields']:
        assert 'name' in f
        assert 'label' in f
        assert 'type' in f
        assert 'value' in f


def test_get_record_total_fields_matches_list():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    assert result['total_fields'] == len(result['fields'])


def test_get_record_carries_field_values():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    by_name = {f['name']: f['value'] for f in result['fields']}
    assert by_name['SIS_ID__c'] == '12345'
    assert by_name['Name'] == 'Jane Doe'


def test_get_record_default_lookup_mode_is_sf_id():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', 'TEST001')
    assert result['lookup_mode'] == 'sf_id'


def test_get_record_external_id_includes_lookup_mode():
    with _patch_sf(_StubSF()):
        result = record_inspector.get_record('dev', 'Account', '12345',
                                             external_id_field='SIS_ID__c')
    assert result['lookup_mode'] == 'external_id:SIS_ID__c'


def test_get_record_raises_when_record_not_found():
    """An empty record payload raises ValueError."""
    with _patch_sf(_StubSF(record={})):
        with pytest.raises(ValueError, match='Record not found'):
            record_inspector.get_record('dev', 'Account', 'MISSING')


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
    with _patch_sf(_StubSF()):
        resp = client.post('/schema/inspect/run',
                           json={'object': 'Account', 'record_id': 'TEST001'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'fields' in body['data']
    assert body['data']['total_fields'] > 0


def test_inspect_run_external_id(client):
    with _patch_sf(_StubSF()):
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
