"""Tests for services.custom_config_viewer and /admin/custom-metadata + /admin/custom-settings routes."""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Service unit tests — Custom Metadata
# ---------------------------------------------------------------------------

def test_get_custom_metadata_types_returns_list():
    from services.custom_config_viewer import get_custom_metadata_types
    result = get_custom_metadata_types('dev')
    assert isinstance(result, list)


def test_mock_cmdts_returns_3_items():
    from services.custom_config_viewer import _mock_cmdts
    result = _mock_cmdts()
    assert len(result) == 3


def test_mock_cmdts_first_item_has_qualified_api_name():
    from services.custom_config_viewer import _mock_cmdts
    first = _mock_cmdts()[0]
    assert 'QualifiedApiName' in first


def test_get_custom_metadata_records_returns_list():
    from services.custom_config_viewer import get_custom_metadata_records
    result = get_custom_metadata_records('dev', 'Integration_Setting__mdt')
    assert isinstance(result, list)


def test_mock_cmdt_records_returns_2_items():
    from services.custom_config_viewer import _mock_cmdt_records
    result = _mock_cmdt_records('Integration_Setting__mdt')
    assert len(result) == 2


def test_mock_cmdt_records_first_item_has_developer_name():
    from services.custom_config_viewer import _mock_cmdt_records
    first = _mock_cmdt_records('Integration_Setting__mdt')[0]
    assert 'DeveloperName' in first


# ---------------------------------------------------------------------------
# Service unit tests — Custom Settings
# ---------------------------------------------------------------------------

def test_get_custom_settings_returns_list():
    from services.custom_config_viewer import get_custom_settings
    result = get_custom_settings('dev')
    assert isinstance(result, list)


def test_mock_custom_settings_returns_2_items():
    from services.custom_config_viewer import _mock_custom_settings
    result = _mock_custom_settings()
    assert len(result) == 2


def test_get_custom_setting_records_returns_list():
    from services.custom_config_viewer import get_custom_setting_records
    result = get_custom_setting_records('dev', 'Integration_Config__c')
    assert isinstance(result, list)


def test_mock_setting_records_items_have_owner_type():
    from services.custom_config_viewer import _mock_setting_records
    records = _mock_setting_records('Integration_Config__c')
    for r in records:
        assert '_owner_type' in r


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_custom_metadata_route_returns_200_and_success(session_client):
    resp = session_client.get('/admin/custom-metadata')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_custom_settings_route_returns_200_and_success(session_client):
    resp = session_client.get('/admin/custom-settings')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


# ---------------------------------------------------------------------------
# Mock-leak regression — with SF_MOCK off, a query failure must NOT silently
# return mock data; it must propagate so the real error surfaces.
# ---------------------------------------------------------------------------

class _RaisingSF:
    def restful(self, *a, **kw):
        raise RuntimeError('tooling api down')

    def query(self, *a, **kw):
        raise RuntimeError('data api down')


def test_custom_metadata_types_error_propagates_when_mock_disabled(monkeypatch):
    from services import custom_config_viewer
    import config
    monkeypatch.setattr(config.Config, 'SF_MOCK', False)
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        custom_config_viewer.get_custom_metadata_types('prod')


def test_custom_settings_error_propagates_when_mock_disabled(monkeypatch):
    from services import custom_config_viewer
    import config
    monkeypatch.setattr(config.Config, 'SF_MOCK', False)
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        custom_config_viewer.get_custom_settings('prod')


def test_custom_metadata_still_mocks_when_mock_enabled(monkeypatch):
    """With SF_MOCK on, a failure still degrades to mock data for dev."""
    from services import custom_config_viewer
    monkeypatch.setattr(custom_config_viewer, 'get_sf', lambda org: _RaisingSF())
    result = custom_config_viewer.get_custom_metadata_types('dev')
    assert isinstance(result, list) and len(result) >= 1
