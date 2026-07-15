"""Tests for alert threshold management in services.org_observer and /observe/thresholds routes."""
import json
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_limits_sf():
    """Return a mock SF client whose restful() returns a minimal limits payload."""
    sf = MagicMock()
    sf.restful.return_value = {
        'DailyApiRequests': {'Max': 15000, 'Remaining': 14000},
        'DataStorageMB':    {'Max': 1024, 'Remaining': 512},
    }
    return sf


# ── Test 1: get_thresholds returns dict (empty when DB unavailable) ────────────
def test_get_thresholds_returns_empty_when_db_unavailable():
    with patch('db.db_available', return_value=False):
        from services.org_observer import get_thresholds
        result = get_thresholds()
    assert isinstance(result, dict)
    assert result == {}


# ── Test 2: set_threshold returns dict with correct keys ──────────────────────
def test_set_threshold_returns_correct_dict_structure():
    with patch('db.db_available', return_value=False):
        from services.org_observer import set_threshold
        result = set_threshold('DailyApiRequests', 40.0, 70.0)
    assert isinstance(result, dict)
    assert result['limit_name'] == 'DailyApiRequests'
    assert result['amber_pct'] == 40.0
    assert result['red_pct'] == 70.0


# ── Test 3: set_threshold saved=False when DB unavailable ─────────────────────
def test_set_threshold_saved_false_when_db_unavailable():
    with patch('db.db_available', return_value=False):
        from services.org_observer import set_threshold
        result = set_threshold('DailyApiRequests', 40.0, 70.0)
    assert result['saved'] is False


# ── Test 4: delete_threshold returns bool ─────────────────────────────────────
def test_delete_threshold_returns_bool_when_db_unavailable():
    with patch('db.db_available', return_value=False):
        from services.org_observer import delete_threshold
        result = delete_threshold('DailyApiRequests')
    assert isinstance(result, bool)
    assert result is False


# ── Test 5: get_limits uses custom threshold when set ─────────────────────────
def test_get_limits_uses_custom_threshold():
    """With DailyApiRequests at ~6.7% used, default=green; custom amber=5 red=10 => amber."""
    sf = _make_limits_sf()
    # 1000 used out of 15000 = 6.667%
    sf.restful.return_value = {
        'DailyApiRequests': {'Max': 15000, 'Remaining': 14000},
    }
    custom_thresholds = {
        'DailyApiRequests': {'amber_pct': 5.0, 'red_pct': 10.0}
    }
    with patch('services.org_observer.get_sf', return_value=sf), \
         patch('services.org_observer.get_thresholds', return_value=custom_thresholds):
        from services.org_observer import get_limits
        result = get_limits('dev')
    limits = result['limits']
    daily = next(l for l in limits if l['key'] == 'DailyApiRequests')
    # 6.667% >= amber 5% but < red 10% → amber
    assert daily['status'] == 'amber'
    assert daily['custom_threshold'] == {'amber_pct': 5.0, 'red_pct': 10.0}


# ── Test 6: get_limits uses default threshold when no custom threshold ─────────
def test_get_limits_uses_default_threshold():
    """With DailyApiRequests at ~6.7% used and no custom threshold, default=green."""
    sf = _make_limits_sf()
    sf.restful.return_value = {
        'DailyApiRequests': {'Max': 15000, 'Remaining': 14000},
    }
    with patch('services.org_observer.get_sf', return_value=sf), \
         patch('services.org_observer.get_thresholds', return_value={}):
        from services.org_observer import get_limits
        result = get_limits('dev')
    limits = result['limits']
    daily = next(l for l in limits if l['key'] == 'DailyApiRequests')
    # 6.667% < 50% → green by default
    assert daily['status'] == 'green'
    assert daily['custom_threshold'] is None


# ── Test 7: GET /api/v1/observe/thresholds → 200 success ─────────────────────
def test_route_get_thresholds_returns_200(client):
    with patch('services.org_observer.get_thresholds', return_value={}):
        resp = client.get('/api/v1/observe/thresholds')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert isinstance(payload['data'], dict)


# ── Test 8: POST /api/v1/observe/thresholds with valid data → 200 success ────
def test_route_post_threshold_valid_returns_200(client):
    saved = {'limit_name': 'DailyApiRequests', 'amber_pct': 40.0, 'red_pct': 70.0, 'saved': True}
    with patch('services.org_observer.set_threshold', return_value=saved):
        resp = client.post(
            '/api/v1/observe/thresholds',
            data=json.dumps({'limit_name': 'DailyApiRequests', 'amber_pct': 40, 'red_pct': 70}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['data']['limit_name'] == 'DailyApiRequests'


# ── Test 9: POST /api/v1/observe/thresholds invalid data (amber > red) → 400 ─
def test_route_post_threshold_invalid_amber_gt_red_returns_400(client):
    resp = client.post(
        '/api/v1/observe/thresholds',
        data=json.dumps({'limit_name': 'DailyApiRequests', 'amber_pct': 80, 'red_pct': 40}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['success'] is False
    assert 'amber_pct' in payload['error']


# ── Test 10: DELETE /api/v1/observe/thresholds/DailyApiRequests → 200 ─────────
def test_route_delete_threshold_returns_200(client):
    with patch('services.org_observer.delete_threshold', return_value=True):
        resp = client.delete('/api/v1/observe/thresholds/DailyApiRequests')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['data']['deleted'] is True


# ── Legacy redirect (mirrors TestMetaLegacyRedirect in test_meta_routes.py) ───

class TestObserveLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/observe/limits', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/observe/limits')

    def test_old_path_redirect_is_followable(self, client):
        with patch('services.org_observer.get_limits', return_value={'limits': []}):
            resp = client.get('/observe/limits', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
