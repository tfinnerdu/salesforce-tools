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
