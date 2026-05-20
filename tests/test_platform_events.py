"""Tests for services.platform_events."""
import pytest


# ── Service-level tests ───────────────────────────────────────────────────────

def test_get_platform_events_mock():
    """With SF_MOCK=true, get_platform_events returns a list with expected keys."""
    from services import platform_events
    result = platform_events.get_platform_events('dev')
    assert isinstance(result, list)
    assert len(result) >= 1
    assert 'id' in result[0]
    assert 'developer_name' in result[0]
    assert 'label' in result[0]
    assert 'description' in result[0]


def test_get_event_members_mock():
    """With SF_MOCK=true, get_event_members returns a list with expected keys."""
    from services import platform_events
    result = platform_events.get_event_members('dev')
    assert isinstance(result, list)
    assert len(result) >= 1
    assert 'id' in result[0]
    assert 'developer_name' in result[0]
    assert 'channel' in result[0]
    assert 'type' in result[0]


def test_get_all_keys():
    """get_all returns a dict with both 'events' and 'members' keys."""
    from services import platform_events
    result = platform_events.get_all('dev')
    assert isinstance(result, dict)
    assert 'events' in result
    assert 'members' in result


def test_mock_events_required_fields():
    """Mock events all have id, developer_name, label, and description."""
    from services import platform_events
    events = platform_events.get_platform_events('dev')
    for ev in events:
        assert 'id' in ev
        assert 'developer_name' in ev
        assert 'label' in ev
        assert 'description' in ev


def test_mock_members_channel_field():
    """Mock members all have a non-empty channel field."""
    from services import platform_events
    members = platform_events.get_event_members('dev')
    for m in members:
        assert 'channel' in m
        assert m['channel']  # non-empty


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_api_platform_events_route(client):
    """GET /admin/platform-events returns 200 with success JSON."""
    resp = client.get('/admin/platform-events')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] is not None


def test_api_platform_events_both_keys(client):
    """Route response data contains both 'events' and 'members' keys."""
    resp = client.get('/admin/platform-events')
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

    resp = client.get('/admin/platform-events')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert 'tooling api down' in data['error']
