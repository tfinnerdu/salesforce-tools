"""Tests for services.merge_history and merge-history routes."""
import pytest
from unittest.mock import patch, MagicMock


# ── Service-level tests ────────────────────────────────────────────────────────

def test_ensure_table_no_error():
    """_ensure_table() should run without raising even when DB is unavailable."""
    from services import merge_history
    # DB is unavailable in test env (DATABASE_URL='') — should be a no-op
    merge_history._ensure_table()  # must not raise


def test_log_merge_records_and_list_retrieves():
    """log_merge() + list_merges() round-trip using mock DB."""
    from services import merge_history

    captured = []

    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = [
        {
            'id': 42,
            'org': 'dev',
            'master_id': '001AAA',
            'victim_id': '001BBB',
            'merged_at': __import__('datetime').datetime(2026, 1, 1, 12, 0, 0),
            'bypass_used': False,
            'status': 'success',
            'error_msg': None,
        }
    ]

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor', return_value=mock_cur):
        merge_history.log_merge('dev', '001AAA', '001BBB', bypass_used=False, status='success')
        result = merge_history.list_merges('dev')

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]['master_id'] == '001AAA'
    assert result[0]['victim_id'] == '001BBB'


def test_list_merges_returns_list():
    """list_merges() always returns a list (falls back to mock when DB unavailable)."""
    from services import merge_history
    result = merge_history.list_merges('dev')
    assert isinstance(result, list)


def test_list_merges_items_have_required_keys():
    """Each item returned by list_merges() has the required audit fields."""
    from services import merge_history
    result = merge_history.list_merges('dev')
    required = {'master_id', 'victim_id', 'merged_at', 'status', 'bypass_used'}
    for item in result:
        missing = required - set(item.keys())
        assert not missing, f"Item missing keys: {missing}"


def test_get_stats_returns_required_keys():
    """get_stats() returns a dict with the four expected summary fields."""
    from services import merge_history
    stats = merge_history.get_stats('dev')
    assert isinstance(stats, dict)
    for key in ('total_merges', 'successful', 'failed', 'bypass_used_count'):
        assert key in stats, f"Missing key: {key}"


def test_mock_returns_three_items_when_db_unavailable():
    """_mock_merges() returns exactly 3 items (covers DB-unavailable fallback)."""
    from services import merge_history
    mocks = merge_history._mock_merges('dev')
    assert isinstance(mocks, list)
    assert len(mocks) == 3


def test_list_merges_returns_empty_when_mock_disabled_and_no_db(monkeypatch):
    """Regression: mock merge data must NOT leak onto a real org.

    Before the fix, list_merges() fell back to _mock_merges() unconditionally
    when the DB was unavailable — so a real sandbox (SF_MOCK=false) with no
    Postgres showed three fake merges. With SF_MOCK off, it must return [].
    """
    from services import merge_history
    import config
    monkeypatch.setattr(config.Config, 'SF_MOCK', False)
    # DB is unavailable in the test env (DATABASE_URL='')
    result = merge_history.list_merges('dev')
    assert result == []


def test_get_stats_returns_zeros_when_mock_disabled_and_no_db(monkeypatch):
    """With SF_MOCK off and no DB, get_stats() returns all-zero counts, not mock stats."""
    from services import merge_history
    import config
    monkeypatch.setattr(config.Config, 'SF_MOCK', False)
    stats = merge_history.get_stats('dev')
    assert stats == {'total_merges': 0, 'successful': 0, 'failed': 0, 'bypass_used_count': 0}


# ── Route-level tests ──────────────────────────────────────────────────────────

def test_merge_history_page_returns_200(session_client):
    """GET /validation/merge-history renders the page (HTTP 200)."""
    resp = session_client.get('/validation/merge-history')
    assert resp.status_code == 200


def test_merge_history_list_api_returns_success(session_client):
    """GET /validation/merge-history/list returns {success: true, data: [...]}."""
    resp = session_client.get('/validation/merge-history/list')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_merge_history_stats_api_returns_success(session_client):
    """GET /validation/merge-history/stats returns {success: true, data: {...}}."""
    resp = session_client.get('/validation/merge-history/stats')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], dict)


def test_duplicate_radar_merge_does_not_raise_if_merge_history_fails():
    """duplicate_radar.merge() must not raise even if merge_history blows up."""
    from services.duplicate_radar import merge

    with patch('services.merge_history._ensure_table', side_effect=RuntimeError('DB dead')), \
         patch('services.merge_history.log_merge', side_effect=RuntimeError('DB dead')):
        # Should complete without exception
        result = merge('dev', master_id='001ABC', victim_id='001DEF')

    assert isinstance(result, dict)
    assert 'success' in result
