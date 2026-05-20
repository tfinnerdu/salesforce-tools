"""Tests for Trace Flag Manager feature."""
import pytest


# ── Service tests ──────────────────────────────────────────────────────────────

def test_list_trace_flags_returns_list():
    from services.apex_log_reader import list_trace_flags
    result = list_trace_flags('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_trace_flags_items_have_required_keys():
    from services.apex_log_reader import list_trace_flags
    result = list_trace_flags('dev')
    required = {'id', 'log_type', 'debug_level_name', 'expired', 'expires_in_minutes'}
    for flag in result:
        assert required.issubset(flag.keys()), f"Flag missing keys: {flag}"


def test_list_trace_flags_expired_flag_detected():
    from services.apex_log_reader import list_trace_flags
    result = list_trace_flags('dev')
    # Mock data includes TF002 which is expired
    expired_flags = [f for f in result if f['expired']]
    assert len(expired_flags) >= 1
    for f in expired_flags:
        assert f['expires_in_minutes'] is None


def test_list_debug_levels_returns_list():
    from services.apex_log_reader import list_debug_levels
    result = list_debug_levels('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_users_for_tracing_returns_list_with_required_keys():
    from services.apex_log_reader import list_users_for_tracing
    result = list_users_for_tracing('dev')
    assert isinstance(result, list)
    assert len(result) > 0
    required = {'id', 'name', 'username'}
    for user in result:
        assert required.issubset(user.keys()), f"User missing keys: {user}"


def test_create_trace_flag_mock_returns_id_and_created():
    from services.apex_log_reader import create_trace_flag
    result = create_trace_flag(
        org='dev',
        entity_id='U001',
        entity_type='User',
        debug_level_id='DL001',
        duration_minutes=30,
    )
    assert result.get('created') is True
    assert 'id' in result


def test_delete_trace_flag_mock_returns_deleted():
    from services.apex_log_reader import delete_trace_flag
    result = delete_trace_flag('dev', 'TF001')
    assert result.get('deleted') is True


def test_delete_expired_trace_flags_returns_count():
    from services.apex_log_reader import delete_expired_trace_flags
    result = delete_expired_trace_flags('dev')
    assert 'deleted_count' in result
    assert isinstance(result['deleted_count'], int)
    assert result['deleted_count'] >= 0


# ── Route tests ────────────────────────────────────────────────────────────────

def test_get_trace_flags_route_returns_200(session_client):
    resp = session_client.get('/logs/trace-flags')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_post_trace_flags_route_returns_200(session_client):
    payload = {
        'entity_id': 'U001',
        'entity_type': 'User',
        'debug_level_id': 'DL001',
        'duration_minutes': 30,
    }
    resp = session_client.post('/logs/trace-flags', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['created'] is True


def test_post_trace_flags_missing_entity_id_returns_400(session_client):
    payload = {
        'debug_level_id': 'DL001',
        'duration_minutes': 30,
    }
    resp = session_client.post('/logs/trace-flags', json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'entity_id' in data['error']


def test_delete_trace_flag_route_returns_200(session_client):
    resp = session_client.delete('/logs/trace-flags/TF001')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['deleted'] is True
