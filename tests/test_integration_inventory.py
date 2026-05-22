"""Tests for services.integration_inventory."""
import pytest


# ── Service-level tests ───────────────────────────────────────────────────────

def test_get_named_credentials_mock():
    """With SF_MOCK=true, should return mock list with at least one item containing 'endpoint'."""
    from services import integration_inventory
    result = integration_inventory.get_named_credentials('dev')
    assert isinstance(result, list)
    assert len(result) >= 1
    assert 'endpoint' in result[0]


def test_get_remote_sites_mock():
    """With SF_MOCK=true, should return mock list with at least one item containing 'url'."""
    from services import integration_inventory
    result = integration_inventory.get_remote_sites('dev')
    assert isinstance(result, list)
    assert len(result) >= 1
    assert 'url' in result[0]


def test_get_connected_apps_mock():
    """With SF_MOCK=true, should return mock list with at least one item containing 'master_label'."""
    from services import integration_inventory
    result = integration_inventory.get_connected_apps('dev')
    assert isinstance(result, list)
    assert len(result) >= 1
    assert 'master_label' in result[0]


def test_get_all_keys():
    """get_all returns dict with all three expected keys."""
    from services import integration_inventory
    result = integration_inventory.get_all('dev')
    assert isinstance(result, dict)
    assert 'named_credentials' in result
    assert 'remote_sites' in result
    assert 'connected_apps' in result


def test_named_credentials_fields():
    """Each named credential has the expected snake_case fields."""
    from services import integration_inventory
    creds = integration_inventory.get_named_credentials('dev')
    for cred in creds:
        assert 'id' in cred
        assert 'developer_name' in cred
        assert 'master_label' in cred
        assert 'endpoint' in cred
        assert 'protocol' in cred


def test_remote_sites_fields():
    """Each remote site has the expected snake_case fields."""
    from services import integration_inventory
    sites = integration_inventory.get_remote_sites('dev')
    for site in sites:
        assert 'id' in site
        assert 'site_name' in site
        assert 'url' in site
        assert 'is_active' in site
        assert 'disable_protocol_security' in site


def test_connected_apps_fields():
    """Each connected app has the expected snake_case fields."""
    from services import integration_inventory
    apps = integration_inventory.get_connected_apps('dev')
    for app in apps:
        assert 'id' in app
        assert 'developer_name' in app
        assert 'master_label' in app
        assert 'description' in app


def test_connected_apps_degrades_on_insufficient_access(monkeypatch):
    """A real-org INSUFFICIENT_ACCESS error degrades to [] so the rest of the
    Integration Inventory page still loads."""
    import services.integration_inventory as inv

    class _DeniedSF:
        def query(self, soql):
            raise Exception('INSUFFICIENT_ACCESS: insufficient access rights '
                            'on cross-reference id')

    monkeypatch.setattr(inv, 'get_sf', lambda org: _DeniedSF())
    monkeypatch.setattr(inv.Config, 'SF_MOCK', False)
    assert inv.get_connected_apps('dev') == []


def test_connected_apps_reraises_unexpected_error(monkeypatch):
    """A non-access error still propagates — only the known cases are swallowed."""
    import services.integration_inventory as inv

    class _BrokenSF:
        def query(self, soql):
            raise RuntimeError('connection reset')

    monkeypatch.setattr(inv, 'get_sf', lambda org: _BrokenSF())
    monkeypatch.setattr(inv.Config, 'SF_MOCK', False)
    with pytest.raises(RuntimeError, match='connection reset'):
        inv.get_connected_apps('dev')


def test_remote_sites_is_active_bool():
    """is_active should be a boolean in mock data."""
    from services import integration_inventory
    sites = integration_inventory.get_remote_sites('dev')
    for site in sites:
        assert isinstance(site['is_active'], bool)


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_api_integrations_route(client):
    """GET /admin/integrations returns 200 with success JSON."""
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
