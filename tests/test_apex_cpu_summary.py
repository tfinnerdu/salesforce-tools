"""Tests for the Apex CPU summary feature (services.apex_log_reader.get_cpu_summary)."""
from unittest.mock import MagicMock, patch

import pytest


def _fake_sf(records):
    """A Salesforce double whose Tooling-API query returns the given ApexLog rows."""
    sf = MagicMock()
    sf.restful.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_LOG_ROWS = [
    {'Id': 'log001', 'LogUser': {'Name': 'Alice'}, 'Operation': 'Execute Anonymous',
     'Status': 'Success', 'LogLength': 1024, 'DurationMilliseconds': 200},
    {'Id': 'log002', 'LogUser': {'Name': 'Bob'}, 'Operation': 'StudentSyncBatch',
     'Status': 'Success', 'LogLength': 4096, 'DurationMilliseconds': 1200},
]


# ── Service tests ──────────────────────────────────────────────────────────────

def test_get_cpu_summary_returns_list():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(_LOG_ROWS)):
        from services.apex_log_reader import get_cpu_summary
        result = get_cpu_summary('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_cpu_summary_items_have_required_keys():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(_LOG_ROWS)):
        from services.apex_log_reader import get_cpu_summary
        result = get_cpu_summary('dev')
    assert len(result) > 0
    required = {'log_id', 'operation', 'duration_ms', 'status_flag', 'user', 'log_length', 'status'}
    for item in result:
        assert required.issubset(item.keys()), f"Item missing keys: {item}"


def test_get_cpu_summary_maps_fields_from_apexlog():
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(_LOG_ROWS)):
        from services.apex_log_reader import get_cpu_summary
        result = get_cpu_summary('dev')
    assert result[0]['log_id'] == 'log001'
    assert result[0]['user'] == 'Alice'
    assert result[0]['operation'] == 'Execute Anonymous'
    assert result[0]['status_flag'] == 'ok'


def test_get_cpu_summary_danger_flag_for_non_success_status():
    from services import apex_log_reader
    rows = [{
        'Id': 'log001', 'LogUser': {'Name': 'Test User'}, 'Operation': 'Execute Anonymous',
        'Status': 'Failure', 'LogLength': 1024, 'DurationMilliseconds': 100,
    }]
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(rows)):
        result = apex_log_reader.get_cpu_summary('dev')
    assert len(result) == 1
    assert result[0]['status_flag'] == 'danger'


def test_get_cpu_summary_warning_flag_for_slow_success():
    from services import apex_log_reader
    rows = [{
        'Id': 'log002', 'LogUser': {'Name': 'Test User'}, 'Operation': 'Execute Anonymous',
        'Status': 'Success', 'LogLength': 2048, 'DurationMilliseconds': 6000,
    }]
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(rows)):
        result = apex_log_reader.get_cpu_summary('dev')
    assert len(result) == 1
    assert result[0]['status_flag'] == 'warning'


# ── Route tests ────────────────────────────────────────────────────────────────

def test_cpu_summary_route_returns_200(session_client):
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(_LOG_ROWS)):
        resp = session_client.get('/logs/apex/cpu-summary')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_cpu_summary_route_data_is_list(session_client):
    with patch('services.apex_log_reader.get_sf', return_value=_fake_sf(_LOG_ROWS)):
        resp = session_client.get('/logs/apex/cpu-summary')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data['data'], list)
    assert len(data['data']) == 2
