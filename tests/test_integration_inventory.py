"""Tests for services.integration_inventory."""
from unittest.mock import MagicMock, patch

import pytest


def _restful_sf(records):
    """SF double whose Tooling-API .restful() returns the given records."""
    sf = MagicMock()
    sf.restful.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


def _full_sf(nc_rows, rss_rows, ca_rows):
    """SF double routing the three queries get_all() issues.

    Named credentials and remote sites go through restful(); connected apps
    go through the standard query().
    """
    def _restful(path, params=None):
        q = (params or {}).get('q', '')
        if 'NamedCredential' in q:
            return {'records': nc_rows, 'totalSize': len(nc_rows), 'done': True}
        if 'RemoteSiteSetting' in q:
            return {'records': rss_rows, 'totalSize': len(rss_rows), 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    sf = MagicMock()
    sf.restful.side_effect = _restful
    sf.query.return_value = {'records': ca_rows, 'totalSize': len(ca_rows), 'done': True}
    return sf


_NC_ROWS = [
    {'Id': '0XA000000000001', 'DeveloperName': 'Conductor_API', 'MasterLabel': 'Conductor API',
     'Endpoint': 'https://conductor.doane.edu', 'Protocol': 'NoAuthentication',
     'PrincipalType': 'NamedUser'},
    {'Id': '0XA000000000002', 'DeveloperName': 'Ethos_API', 'MasterLabel': 'Ethos API',
     'Endpoint': 'https://integrate.elluciancloud.com', 'Protocol': 'Oauth',
     'PrincipalType': 'NamedUser'},
]

_RSS_ROWS = [
    {'Id': '0rp000000000001', 'SiteName': 'Conductor', 'Description': 'Conductor host',
     'EndpointUrl': 'https://conductor.doane.edu', 'IsActive': True},
    {'Id': '0rp000000000002', 'SiteName': 'Legacy', 'Description': '',
     'EndpointUrl': 'https://old.doane.edu', 'IsActive': False},
]

_CA_ROWS = [
    {'Id': '0CA000000000001', 'Name': 'Mission Control'},
    {'Id': '0CA000000000002', 'Name': 'Data Loader'},
]


# ── Service-level tests ───────────────────────────────────────────────────────

def test_get_named_credentials():
    """get_named_credentials maps NamedCredential rows including 'endpoint'."""
    from services import integration_inventory
    with patch('services.integration_inventory.get_sf', return_value=_restful_sf(_NC_ROWS)):
        result = integration_inventory.get_named_credentials('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    assert 'endpoint' in result[0]
    assert result[0]['endpoint'] == 'https://conductor.doane.edu'


def test_get_remote_sites():
    """get_remote_sites maps RemoteSiteSetting rows including 'url'."""
    from services import integration_inventory
    with patch('services.integration_inventory.get_sf', return_value=_restful_sf(_RSS_ROWS)):
        result = integration_inventory.get_remote_sites('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    assert 'url' in result[0]


def test_get_connected_apps():
    """get_connected_apps maps ConnectedApplication rows including 'master_label'."""
    from services import integration_inventory

    sf = MagicMock()
    sf.query.return_value = {'records': _CA_ROWS, 'totalSize': len(_CA_ROWS), 'done': True}
    with patch('services.integration_inventory.get_sf', return_value=sf):
        result = integration_inventory.get_connected_apps('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    assert 'master_label' in result[0]
    assert result[0]['master_label'] == 'Mission Control'


def test_get_all_keys():
    """get_all returns dict with all three expected keys."""
    from services import integration_inventory
    sf = _full_sf(_NC_ROWS, _RSS_ROWS, _CA_ROWS)
    with patch('services.integration_inventory.get_sf', return_value=sf):
        result = integration_inventory.get_all('dev')
    assert isinstance(result, dict)
    assert 'named_credentials' in result
    assert 'remote_sites' in result
    assert 'connected_apps' in result
    assert len(result['named_credentials']) == 2
    assert len(result['connected_apps']) == 2


def test_named_credentials_fields():
    """Each named credential has the expected snake_case fields."""
    from services import integration_inventory
    with patch('services.integration_inventory.get_sf', return_value=_restful_sf(_NC_ROWS)):
        creds = integration_inventory.get_named_credentials('dev')
    for cred in creds:
        for key in ('id', 'developer_name', 'master_label', 'endpoint', 'protocol'):
            assert key in cred


def test_remote_sites_fields():
    """Each remote site has the expected snake_case fields."""
    from services import integration_inventory
    with patch('services.integration_inventory.get_sf', return_value=_restful_sf(_RSS_ROWS)):
        sites = integration_inventory.get_remote_sites('dev')
    for site in sites:
        for key in ('id', 'site_name', 'url', 'is_active', 'disable_protocol_security'):
            assert key in site


def test_connected_apps_fields():
    """Each connected app has the expected snake_case fields."""
    from services import integration_inventory
    sf = MagicMock()
    sf.query.return_value = {'records': _CA_ROWS, 'totalSize': len(_CA_ROWS), 'done': True}
    with patch('services.integration_inventory.get_sf', return_value=sf):
        apps = integration_inventory.get_connected_apps('dev')
    for app in apps:
        for key in ('id', 'developer_name', 'master_label', 'description'):
            assert key in app


def test_connected_apps_degrades_on_insufficient_access(monkeypatch):
    """An INSUFFICIENT_ACCESS error degrades to [] so the rest of the
    Integration Inventory page still loads."""
    import services.integration_inventory as inv

    class _DeniedSF:
        def query(self, soql):
            raise Exception('INSUFFICIENT_ACCESS: insufficient access rights '
                            'on cross-reference id')

    monkeypatch.setattr(inv, 'get_sf', lambda org: _DeniedSF())
    assert inv.get_connected_apps('dev') == []


def test_connected_apps_reraises_unexpected_error(monkeypatch):
    """A non-access error still propagates — only the known cases are swallowed."""
    import services.integration_inventory as inv

    class _BrokenSF:
        def query(self, soql):
            raise RuntimeError('connection reset')

    monkeypatch.setattr(inv, 'get_sf', lambda org: _BrokenSF())
    with pytest.raises(RuntimeError, match='connection reset'):
        inv.get_connected_apps('dev')


def test_remote_sites_is_active_bool():
    """is_active is coerced to a boolean."""
    from services import integration_inventory
    with patch('services.integration_inventory.get_sf', return_value=_restful_sf(_RSS_ROWS)):
        sites = integration_inventory.get_remote_sites('dev')
    for site in sites:
        assert isinstance(site['is_active'], bool)
    by_name = {s['site_name']: s for s in sites}
    assert by_name['Conductor']['is_active'] is True
    assert by_name['Legacy']['is_active'] is False


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_api_integrations_route(client):
    """GET /admin/integrations returns 200 with success JSON."""
    sf = _full_sf(_NC_ROWS, _RSS_ROWS, _CA_ROWS)
    with patch('services.integration_inventory.get_sf', return_value=sf):
        resp = client.get('/admin/integrations')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] is not None
    assert 'named_credentials' in data['data']
    assert 'remote_sites' in data['data']
    assert 'connected_apps' in data['data']


def test_api_integrations_error(client, monkeypatch):
    """When integration_inventory.get_all raises, the route returns 500."""
    def _boom(org):
        raise RuntimeError('tooling api down')

    import services.integration_inventory as inv
    monkeypatch.setattr(inv, 'get_all', _boom)

    resp = client.get('/admin/integrations')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert 'tooling api down' in data['error']
