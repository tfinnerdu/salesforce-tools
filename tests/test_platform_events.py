"""Tests for services.platform_events.

Canonical example of the post-mock-removal test pattern: each test patches
`get_sf` in the service module's namespace with a `unittest.mock` double
configured to return the Salesforce response shape that test needs.
"""
from unittest.mock import MagicMock, patch

import pytest


def _fake_sf(records):
    """A Salesforce double whose Tooling-API query returns the given records."""
    sf = MagicMock()
    sf.restful.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_EVENT_ROWS = [
    {'Id': '0PE000000000001', 'DeveloperName': 'Order_Event__chn', 'MasterLabel': 'Order Event'},
    {'Id': '0PE000000000002', 'DeveloperName': 'Sync_Event__chn', 'MasterLabel': 'Sync Event'},
]
_MEMBER_ROWS = [
    {'Id': '0PM000000000001', 'DeveloperName': 'Order_Member',
     'MasterLabel': 'Order Member', 'EventChannel': 'Order_Event__chn'},
]


# ── Service-level tests ───────────────────────────────────────────────────────

def test_get_platform_events_returns_mapped_list():
    """get_platform_events maps PlatformEventChannel rows to the API shape."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf(_EVENT_ROWS)):
        from services import platform_events
        result = platform_events.get_platform_events('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]['id'] == '0PE000000000001'
    assert result[0]['developer_name'] == 'Order_Event__chn'
    assert result[0]['label'] == 'Order Event'
    # PlatformEventChannel has no Description field in the Tooling API.
    assert 'description' not in result[0]


def test_get_platform_events_empty_when_no_records():
    """A real org with no PlatformEventChannels yields an empty list, not mock data."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf([])):
        from services import platform_events
        result = platform_events.get_platform_events('dev')
    assert result == []


def test_get_event_members_returns_mapped_list():
    """get_event_members maps PlatformEventChannelMember rows to the API shape."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf(_MEMBER_ROWS)):
        from services import platform_events
        result = platform_events.get_event_members('dev')
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]['id'] == '0PM000000000001'
    assert result[0]['developer_name'] == 'Order_Member'
    assert result[0]['channel'] == 'Order_Event__chn'
    assert result[0]['type'] == ''


def test_get_all_returns_events_and_members():
    """get_all returns a dict with both 'events' and 'members' keys."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf(_EVENT_ROWS)):
        from services import platform_events
        result = platform_events.get_all('dev')
    assert isinstance(result, dict)
    assert 'events' in result
    assert 'members' in result


def test_get_sf_called_with_requested_org():
    """The service connects to the org it is asked for."""
    fake = _fake_sf(_EVENT_ROWS)
    with patch('services.platform_events.get_sf', return_value=fake) as mock_get_sf:
        from services import platform_events
        platform_events.get_platform_events('prod')
    mock_get_sf.assert_called_once_with('prod')


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_api_platform_events_route(client):
    """GET /admin/platform-events returns 200 with success JSON."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf(_EVENT_ROWS)):
        resp = client.get('/api/v1/admin/platform-events')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] is not None


def test_api_platform_events_both_keys(client):
    """Route response data contains both 'events' and 'members' keys."""
    with patch('services.platform_events.get_sf', return_value=_fake_sf(_EVENT_ROWS)):
        resp = client.get('/api/v1/admin/platform-events')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'events' in data['data']
    assert 'members' in data['data']


def test_api_platform_events_error(client, monkeypatch):
    """When platform_events.get_all raises, the route returns 500."""
    def _boom(org):
        raise RuntimeError('tooling api down')

    import services.platform_events as pe
    monkeypatch.setattr(pe, 'get_all', _boom)

    resp = client.get('/api/v1/admin/platform-events')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert 'tooling api down' in data['error']
