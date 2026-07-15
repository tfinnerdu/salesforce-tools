"""Tests for services.custom_config_viewer and /admin/custom-metadata + /admin/custom-settings routes."""
from unittest.mock import MagicMock, patch

import pytest


def _restful_sf(records):
    """SF double whose Tooling-API .restful() returns the given records."""
    sf = MagicMock()
    sf.restful.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


def _query_sf(records):
    """SF double whose .query() returns the given records."""
    sf = MagicMock()
    sf.query.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_CMDT_ENTITY_ROWS = [
    {'QualifiedApiName': 'Integration_Setting__mdt', 'Label': 'Integration Setting'},
    {'QualifiedApiName': 'Feature_Flag__mdt', 'Label': 'Feature Flag'},
    {'QualifiedApiName': 'Mapping_Rule__mdt', 'Label': 'Mapping Rule'},
]

_CMDT_RECORD_ROWS = [
    {'Id': 'm00000000000001', 'DeveloperName': 'Conductor', 'Label': 'Conductor',
     'MasterLabel': 'Conductor'},
    {'Id': 'm00000000000002', 'DeveloperName': 'Ethos', 'Label': 'Ethos',
     'MasterLabel': 'Ethos'},
]

_CUSTOM_SETTING_ROWS = [
    {'QualifiedApiName': 'Integration_Config__c', 'Label': 'Integration Config',
     'InternalSharingModel': 'ReadWrite'},
    {'QualifiedApiName': 'Sync_Toggle__c', 'Label': 'Sync Toggle',
     'InternalSharingModel': 'Private'},
]


# ---------------------------------------------------------------------------
# Service unit tests — Custom Metadata
# ---------------------------------------------------------------------------

def test_get_custom_metadata_types_returns_list():
    from services.custom_config_viewer import get_custom_metadata_types
    with patch('services.custom_config_viewer.get_sf', return_value=_restful_sf(_CMDT_ENTITY_ROWS)):
        result = get_custom_metadata_types('dev')
    assert isinstance(result, list)
    assert len(result) == 3


def test_get_custom_metadata_types_records_have_qualified_api_name():
    from services.custom_config_viewer import get_custom_metadata_types
    with patch('services.custom_config_viewer.get_sf', return_value=_restful_sf(_CMDT_ENTITY_ROWS)):
        result = get_custom_metadata_types('dev')
    for r in result:
        assert 'QualifiedApiName' in r
    assert result[0]['QualifiedApiName'] == 'Integration_Setting__mdt'


def test_get_custom_metadata_records_returns_list():
    from services.custom_config_viewer import get_custom_metadata_records
    with patch('services.custom_config_viewer.get_sf', return_value=_query_sf(_CMDT_RECORD_ROWS)):
        result = get_custom_metadata_records('dev', 'Integration_Setting__mdt')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_custom_metadata_records_have_developer_name():
    from services.custom_config_viewer import get_custom_metadata_records
    with patch('services.custom_config_viewer.get_sf', return_value=_query_sf(_CMDT_RECORD_ROWS)):
        result = get_custom_metadata_records('dev', 'Integration_Setting__mdt')
    for r in result:
        assert 'DeveloperName' in r


# ---------------------------------------------------------------------------
# Service unit tests — Custom Settings
# ---------------------------------------------------------------------------

def test_get_custom_settings_returns_list():
    from services.custom_config_viewer import get_custom_settings
    with patch('services.custom_config_viewer.get_sf', return_value=_restful_sf(_CUSTOM_SETTING_ROWS)):
        result = get_custom_settings('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_custom_setting_records_returns_list():
    from services.custom_config_viewer import get_custom_setting_records
    rows = [
        {'Id': 'a00000000000001', 'Name': 'Default', 'SetupOwnerId': '00D000000000001'},
        {'Id': 'a00000000000002', 'Name': 'Override', 'SetupOwnerId': '005000000000001'},
    ]
    with patch('services.custom_config_viewer.get_sf', return_value=_query_sf(rows)):
        result = get_custom_setting_records('dev', 'Integration_Config__c')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_custom_setting_records_have_owner_type():
    from services.custom_config_viewer import get_custom_setting_records
    rows = [
        {'Id': 'a00000000000001', 'Name': 'Default', 'SetupOwnerId': '00D000000000001'},
        {'Id': 'a00000000000002', 'Name': 'ProfileLvl', 'SetupOwnerId': '00e000000000001'},
        {'Id': 'a00000000000003', 'Name': 'UserLvl', 'SetupOwnerId': '005000000000001'},
    ]
    with patch('services.custom_config_viewer.get_sf', return_value=_query_sf(rows)):
        records = get_custom_setting_records('dev', 'Integration_Config__c')
    owner_types = [r['_owner_type'] for r in records]
    assert owner_types == ['Org', 'Profile', 'User']


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_custom_metadata_route_returns_200_and_success(session_client):
    with patch('services.custom_config_viewer.get_sf', return_value=_restful_sf(_CMDT_ENTITY_ROWS)):
        resp = session_client.get('/api/v1/admin/custom-metadata')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['data']) == 3


def test_custom_settings_route_returns_200_and_success(session_client):
    with patch('services.custom_config_viewer.get_sf', return_value=_restful_sf(_CUSTOM_SETTING_ROWS)):
        resp = session_client.get('/api/v1/admin/custom-settings')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['data']) == 2


# ---------------------------------------------------------------------------
# Error propagation — a query failure must NOT be silently swallowed; it must
# propagate so the real error surfaces (there is no mock-data fallback).
# ---------------------------------------------------------------------------

class _RaisingSF:
    def restful(self, *a, **kw):
        raise RuntimeError('tooling api down')

    def query(self, *a, **kw):
        raise RuntimeError('data api down')


def test_custom_metadata_types_error_propagates(monkeypatch):
    from services import custom_config_viewer
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError, match='tooling api down'):
        custom_config_viewer.get_custom_metadata_types('prod')


def test_custom_settings_error_propagates(monkeypatch):
    from services import custom_config_viewer
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError, match='tooling api down'):
        custom_config_viewer.get_custom_settings('prod')


def test_custom_metadata_records_error_propagates(monkeypatch):
    from services import custom_config_viewer
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError, match='data api down'):
        custom_config_viewer.get_custom_metadata_records('prod', 'Integration_Setting__mdt')
