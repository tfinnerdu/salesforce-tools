"""Tests for the Trace Flag Manager feature (services.apex_log_reader)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000+0000')


_FUTURE = datetime.now(timezone.utc) + timedelta(hours=2)
_PAST = datetime.now(timezone.utc) - timedelta(hours=2)

_TRACE_FLAG_ROWS = [
    {'Id': 'TF001', 'LogType': 'USER_DEBUG', 'StartDate': _iso(_PAST),
     'ExpirationDate': _iso(_FUTURE), 'TracedEntityId': '005000000000001',
     'DebugLevel': {'DeveloperName': 'SFDC_DevConsole', 'Id': 'DL001'}},
    {'Id': 'TF002', 'LogType': 'USER_DEBUG', 'StartDate': _iso(_PAST),
     'ExpirationDate': _iso(_PAST), 'TracedEntityId': '01p000000000001',
     'DebugLevel': {'DeveloperName': 'SF_ApexDebug', 'Id': 'DL002'}},
]
_DEBUG_LEVEL_ROWS = [
    {'Id': 'DL001', 'DeveloperName': 'SFDC_DevConsole', 'MasterLabel': 'Dev Console'},
    {'Id': 'DL002', 'DeveloperName': 'SF_ApexDebug', 'MasterLabel': 'Apex Debug'},
]
_USER_ROWS = [
    {'Id': '005000000000001', 'Name': 'Alice Admin', 'Username': 'alice@doane.edu'},
    {'Id': '005000000000002', 'Name': 'Bob Dev', 'Username': 'bob@doane.edu'},
]


def _fake_sf(trace_rows=None, debug_rows=None, user_rows=None):
    """A Salesforce double routing Tooling-API and Data-API calls by SOQL content."""
    trace_rows = _TRACE_FLAG_ROWS if trace_rows is None else trace_rows
    debug_rows = _DEBUG_LEVEL_ROWS if debug_rows is None else debug_rows
    user_rows = _USER_ROWS if user_rows is None else user_rows
    sf = MagicMock()

    def restful(path, method='GET', params=None, json=None):
        if method == 'POST':
            return {'id': 'TF_NEW_001', 'success': True}
        if method == 'DELETE':
            return {}
        q = (params or {}).get('q', '')
        if 'FROM TraceFlag' in q:
            return {'records': trace_rows, 'totalSize': len(trace_rows), 'done': True}
        if 'FROM DebugLevel' in q:
            return {'records': debug_rows, 'totalSize': len(debug_rows), 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    def query(soql):
        return {'records': user_rows, 'totalSize': len(user_rows), 'done': True}

    sf.restful.side_effect = restful
    sf.query.side_effect = query
    return sf


# ── Service tests ──────────────────────────────────────────────────────────────

def test_list_trace_flags_returns_list():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import list_trace_flags
        result = list_trace_flags('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_list_trace_flags_items_have_required_keys():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import list_trace_flags
        result = list_trace_flags('dev')
    required = {'id', 'log_type', 'debug_level_name', 'expired', 'expires_in_minutes'}
    for flag in result:
        assert required.issubset(flag.keys()), f"Flag missing keys: {flag}"


def test_list_trace_flags_expired_flag_detected():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import list_trace_flags
        result = list_trace_flags('dev')
    # TF002 has a past ExpirationDate and must be flagged expired.
    expired_flags = [f for f in result if f['expired']]
    assert len(expired_flags) == 1
    assert expired_flags[0]['id'] == 'TF002'
    for f in expired_flags:
        assert f['expires_in_minutes'] is None
    # TF001 is in the future — not expired, has a positive minutes-remaining.
    active = [f for f in result if not f['expired']]
    assert len(active) == 1
    assert active[0]['expires_in_minutes'] > 0


def test_list_debug_levels_returns_list():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import list_debug_levels
        result = list_debug_levels('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]['id'] == 'DL001'


def test_list_users_for_tracing_returns_list_with_required_keys():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import list_users_for_tracing
        result = list_users_for_tracing('dev')
    assert isinstance(result, list)
    assert len(result) == 2
    required = {'id', 'name', 'username'}
    for user in result:
        assert required.issubset(user.keys()), f"User missing keys: {user}"


def test_create_trace_flag_returns_id_and_created():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import create_trace_flag
        result = create_trace_flag(
            org='dev',
            entity_id='U001',
            entity_type='User',
            debug_level_id='DL001',
            duration_minutes=30,
        )
    assert result.get('created') is True
    assert result['id'] == 'TF_NEW_001'


def test_delete_trace_flag_returns_deleted():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import delete_trace_flag
        result = delete_trace_flag('dev', 'TF001')
    assert result.get('deleted') is True


def test_delete_expired_trace_flags_returns_count():
    """delete_expired_trace_flags deletes only flags past their expiration."""
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        from services.apex_log_reader import delete_expired_trace_flags
        result = delete_expired_trace_flags('dev')
    assert 'deleted_count' in result
    # Exactly one flag (TF002) is expired in the fixture.
    assert result['deleted_count'] == 1


# ── Route tests ────────────────────────────────────────────────────────────────

def test_get_trace_flags_route_returns_200(session_client):
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        resp = session_client.get('/api/v1/logs/trace-flags')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert len(data['data']) == 2


def test_post_trace_flags_route_returns_200(session_client):
    payload = {
        'entity_id': 'U001',
        'entity_type': 'User',
        'debug_level_id': 'DL001',
        'duration_minutes': 30,
    }
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        resp = session_client.post('/api/v1/logs/trace-flags', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['created'] is True


def test_post_trace_flags_missing_entity_id_returns_400(session_client):
    payload = {
        'debug_level_id': 'DL001',
        'duration_minutes': 30,
    }
    resp = session_client.post('/api/v1/logs/trace-flags', json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'entity_id' in data['error']


def test_delete_trace_flag_route_returns_200(session_client):
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
        resp = session_client.delete('/api/v1/logs/trace-flags/TF001')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['deleted'] is True


class TestLogsLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/logs/trace-flags', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/logs/trace-flags')

    def test_old_path_redirect_is_followable(self, client, monkeypatch):
        with patch('services.apex_log_reader.get_sf', return_value=_fake_sf()):
            resp = client.get('/logs/trace-flags', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


# ── _entity_type_from_id — TraceFlag has no TracedEntityType column ───────────

@pytest.mark.parametrize('record_id,expected', [
    ('005000000000000001', 'User'),
    ('01p000000000000001', 'ApexClass'),
    ('01q000000000000001', 'ApexTrigger'),
    ('001000000000000001', ''),          # unknown prefix
    ('', ''),
])
def test_entity_type_from_id(record_id, expected):
    from services.apex_log_reader import _entity_type_from_id
    assert _entity_type_from_id(record_id) == expected
