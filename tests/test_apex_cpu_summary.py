"""Tests for Apex CPU summary feature."""
import pytest


# ── Service tests ──────────────────────────────────────────────────────────────

def test_get_cpu_summary_returns_list():
    from services.apex_log_reader import get_cpu_summary
    result = get_cpu_summary('dev')
    assert isinstance(result, list)


def test_get_cpu_summary_items_have_required_keys():
    from services.apex_log_reader import get_cpu_summary
    result = get_cpu_summary('dev')
    assert len(result) > 0
    required = {'log_id', 'operation', 'duration_ms', 'status_flag', 'user', 'log_length', 'status'}
    for item in result:
        assert required.issubset(item.keys()), f"Item missing keys: {item}"


def test_get_cpu_summary_danger_flag_for_non_success_status(monkeypatch):
    from services import apex_log_reader
    from sf_provider import MockSalesforce

    # Patch to return a record with non-Success status
    class PatchedSF:
        def restful(self, path, method='GET', **kwargs):
            return {
                'records': [{
                    'Id': 'log001',
                    'LogUser': {'Name': 'Test User'},
                    'Operation': 'Execute Anonymous',
                    'Status': 'Failure',
                    'LogLength': 1024,
                    'DurationMilliseconds': 100,
                }]
            }

    monkeypatch.setattr(apex_log_reader, 'get_sf', lambda org: PatchedSF())
    result = apex_log_reader.get_cpu_summary('dev')
    assert len(result) == 1
    assert result[0]['status_flag'] == 'danger'


def test_get_cpu_summary_warning_flag_for_slow_success(monkeypatch):
    from services import apex_log_reader

    class PatchedSF:
        def restful(self, path, method='GET', **kwargs):
            return {
                'records': [{
                    'Id': 'log002',
                    'LogUser': {'Name': 'Test User'},
                    'Operation': 'Execute Anonymous',
                    'Status': 'Success',
                    'LogLength': 2048,
                    'DurationMilliseconds': 6000,
                }]
            }

    monkeypatch.setattr(apex_log_reader, 'get_sf', lambda org: PatchedSF())
    result = apex_log_reader.get_cpu_summary('dev')
    assert len(result) == 1
    assert result[0]['status_flag'] == 'warning'


# ── Route tests ────────────────────────────────────────────────────────────────

def test_cpu_summary_route_returns_200(session_client):
    resp = session_client.get('/logs/apex/cpu-summary')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_cpu_summary_route_data_is_list(session_client):
    resp = session_client.get('/logs/apex/cpu-summary')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data['data'], list)
