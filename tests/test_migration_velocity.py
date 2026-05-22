"""Tests for the Migration Velocity & ETA service and routes."""
import pytest
from unittest.mock import patch


# ── Service unit tests ────────────────────────────────────────────────────────

def test_get_velocity_data_returns_required_keys():
    """get_velocity_data returns a dict with all required top-level keys."""
    from services.migration_velocity import get_velocity_data
    result = get_velocity_data(org='dev', days=30)
    assert isinstance(result, dict)
    for key in ('daily', 'velocity_avg', 'eta_date', 'total_migrated', 'target', 'pct_complete'):
        assert key in result, f"Missing key: {key}"


def test_mock_velocity_daily_list_length():
    """_mock_velocity(30) returns a daily list with exactly 31 items (days + today)."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    assert len(result['daily']) == 31


def test_mock_velocity_pct_complete_range():
    """_mock_velocity pct_complete is a float between 0 and 100 inclusive."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    pct = result['pct_complete']
    assert isinstance(pct, float)
    assert 0.0 <= pct <= 100.0


def test_mock_velocity_velocity_avg_positive():
    """_mock_velocity returns a velocity_avg greater than 0."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    assert result['velocity_avg'] > 0


def test_mock_velocity_target_value():
    """_mock_velocity target equals the PersonAccount universe constant (4312)."""
    from services.migration_velocity import _mock_velocity, TOTAL_RECORDS_TARGET
    result = _mock_velocity(30)
    assert result['target'] == 4312
    assert result['target'] == TOTAL_RECORDS_TARGET


def test_mock_velocity_eta_date_type():
    """_mock_velocity eta_date is either a string or None."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    assert result['eta_date'] is None or isinstance(result['eta_date'], str)


def test_mock_velocity_daily_item_keys():
    """Each item in _mock_velocity daily list contains date, records, and cumulative keys."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    for item in result['daily']:
        assert 'date' in item
        assert 'records' in item
        assert 'cumulative' in item


def test_mock_velocity_cumulative_monotonic():
    """_mock_velocity cumulative values are monotonically non-decreasing."""
    from services.migration_velocity import _mock_velocity
    result = _mock_velocity(30)
    cumulative_values = [item['cumulative'] for item in result['daily']]
    for i in range(1, len(cumulative_values)):
        assert cumulative_values[i] >= cumulative_values[i - 1], (
            f"Cumulative decreased at index {i}: "
            f"{cumulative_values[i-1]} -> {cumulative_values[i]}"
        )


# ── Route integration tests ───────────────────────────────────────────────────

def test_velocity_page_returns_200(client):
    """GET /migration/velocity returns HTTP 200."""
    resp = client.get('/migration/velocity')
    assert resp.status_code == 200


def test_velocity_data_api_returns_success(client):
    """GET /migration/velocity/data returns 200 with success:true and data payload."""
    resp = client.get('/migration/velocity/data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data'] is not None
    assert 'daily' in body['data']
    assert 'pct_complete' in body['data']


# ── list_recent_batches + /migration/batches/recent ───────────────────────────

def test_list_recent_batches_returns_list():
    """list_recent_batches always returns a list (empty when no DB)."""
    from services import migration_velocity
    result = migration_velocity.list_recent_batches('dev')
    assert isinstance(result, list)


def test_list_recent_batches_maps_db_rows(monkeypatch):
    """DB rows are mapped to {date, records, status} for the dashboard widget."""
    from services import migration_velocity
    monkeypatch.setattr(migration_velocity, '_get_batches_from_db', lambda org: [
        {'started_at': '2026-05-20T08:00:00', 'records_processed': 120},
        {'started_at': '2026-05-19T08:00:00', 'records_processed': 95},
    ])
    rows = migration_velocity.list_recent_batches('prod')
    assert len(rows) == 2
    assert rows[0]['records'] == 120
    assert rows[0]['status'] == 'Completed'


def test_batches_recent_route_returns_success(client):
    """GET /migration/batches/recent returns 200 (regression — was a 404)."""
    resp = client.get('/migration/batches/recent')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data'], list)
