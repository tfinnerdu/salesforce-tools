"""Tests for the Migration Velocity & ETA service and routes.

The fabricated mock-data layer is gone: there is no ``_mock_velocity`` and no
``TOTAL_RECORDS_TARGET`` constant. ``target`` now comes from
``Config.MIGRATION_RECORD_TARGET`` (default 0) and an empty DB yields a zeroed
payload from ``_empty_velocity``. Tests drive ``get_velocity_data`` directly by
patching ``_get_batches_from_db``.
"""
import pytest
from unittest.mock import patch


def _batch_rows(per_day):
    """Build fake migration_batches rows: per_day is a list of (date, records)."""
    return [
        {'started_at': f'{date}T08:00:00', 'created_at': f'{date}T08:00:00',
         'records_processed': records}
        for date, records in per_day
    ]


# ── Service unit tests: get_velocity_data ─────────────────────────────────────

def test_get_velocity_data_returns_required_keys():
    """get_velocity_data returns a dict with all required top-level keys."""
    from services.migration_velocity import get_velocity_data
    result = get_velocity_data(org='dev', days=30)
    assert isinstance(result, dict)
    for key in ('daily', 'velocity_avg', 'eta_date', 'total_migrated', 'target', 'pct_complete'):
        assert key in result, f"Missing key: {key}"


def test_empty_velocity_daily_list_length():
    """An empty-DB run returns a daily list with exactly 31 items (days + today)."""
    from services import migration_velocity
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=[]):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    assert len(result['daily']) == 31


def test_empty_velocity_is_zeroed():
    """With no batch data, the payload is fully zeroed."""
    from services import migration_velocity
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=[]):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    assert result['total_migrated'] == 0
    assert result['velocity_avg'] == 0
    assert result['eta_date'] is None
    assert result['pct_complete'] == 0.0


def test_velocity_pct_complete_range():
    """pct_complete stays within 0..100 when batch data and a target are present."""
    from services import migration_velocity
    from config import Config
    today = __import__('datetime').datetime.now(
        __import__('datetime').timezone.utc).date()
    rows = _batch_rows([(today.isoformat(), 500), ((today.replace()).isoformat(), 0)])
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=rows), \
         patch.object(Config, 'MIGRATION_RECORD_TARGET', 4000):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    pct = result['pct_complete']
    assert isinstance(pct, float)
    assert 0.0 <= pct <= 100.0


def test_velocity_avg_positive_with_data():
    """velocity_avg is greater than 0 when recent days have records."""
    from services import migration_velocity
    import datetime as dt
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = _batch_rows([
        ((today - dt.timedelta(days=1)).isoformat(), 100),
        (today.isoformat(), 200),
    ])
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=rows):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    assert result['velocity_avg'] > 0


def test_velocity_target_from_config(monkeypatch):
    """target comes straight from Config.MIGRATION_RECORD_TARGET."""
    from services import migration_velocity
    from config import Config
    monkeypatch.setattr(Config, 'MIGRATION_RECORD_TARGET', 4312)
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=[]):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    assert result['target'] == 4312


def test_velocity_target_defaults_to_zero():
    """With no MIGRATION_RECORD_TARGET configured, target is 0 (Config default)."""
    from services.migration_velocity import get_velocity_data
    result = get_velocity_data(org='dev', days=30)
    assert result['target'] == 0


def test_velocity_eta_date_type():
    """eta_date is either a string or None."""
    from services.migration_velocity import get_velocity_data
    result = get_velocity_data(org='dev', days=30)
    assert result['eta_date'] is None or isinstance(result['eta_date'], str)


def test_velocity_eta_date_computed_when_target_set(monkeypatch):
    """With recent velocity and a remaining target, an ETA date string is produced."""
    from services import migration_velocity
    from config import Config
    import datetime as dt
    monkeypatch.setattr(Config, 'MIGRATION_RECORD_TARGET', 100000)
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = _batch_rows([
        ((today - dt.timedelta(days=1)).isoformat(), 200),
        (today.isoformat(), 200),
    ])
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=rows):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
    assert isinstance(result['eta_date'], str)


def test_velocity_daily_item_keys():
    """Each item in the daily list contains date, records, and cumulative keys."""
    from services.migration_velocity import get_velocity_data
    result = get_velocity_data(org='dev', days=30)
    for item in result['daily']:
        assert 'date' in item
        assert 'records' in item
        assert 'cumulative' in item


def test_velocity_cumulative_monotonic():
    """Cumulative values are monotonically non-decreasing."""
    from services import migration_velocity
    import datetime as dt
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = _batch_rows([
        ((today - dt.timedelta(days=5)).isoformat(), 50),
        ((today - dt.timedelta(days=2)).isoformat(), 80),
        (today.isoformat(), 120),
    ])
    with patch.object(migration_velocity, '_get_batches_from_db', return_value=rows):
        result = migration_velocity.get_velocity_data(org='dev', days=30)
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
