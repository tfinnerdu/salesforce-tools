"""Tests for services.sandbox_drift."""
import pytest
from unittest.mock import MagicMock, patch


def _make_sf_mock(count):
    sf = MagicMock()
    sf.query.return_value = {'totalSize': count, 'done': True, 'records': []}
    return sf


def _patch_two_orgs(base_count, target_count):
    """Return a context manager that patches get_sf with two separate mock objects."""
    sf_base = _make_sf_mock(base_count)
    sf_target = _make_sf_mock(target_count)
    orgs = {}

    def side_effect(org):
        if org not in orgs:
            if not orgs:
                orgs[org] = sf_base
            else:
                orgs[org] = sf_target
        return orgs[org]

    return patch('services.sandbox_drift.get_sf', side_effect=side_effect)


# ── Test 1: run() returns dict with expected top-level keys ───────────────────
def test_run_returns_dict_with_required_keys():
    with _patch_two_orgs(1000, 980):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    assert isinstance(result, dict)
    assert 'baseline_org' in result
    assert 'target_org' in result
    assert 'checks' in result
    assert 'run_at' in result


# ── Test 2: checks list has exactly 11 items ──────────────────────────────────
def test_checks_list_has_11_items():
    with _patch_two_orgs(500, 490):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    assert len(result['checks']) == 11


# ── Test 3: each check has required fields ────────────────────────────────────
def test_each_check_has_required_fields():
    with _patch_two_orgs(300, 295):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    for check in result['checks']:
        assert 'label' in check
        assert 'baseline_count' in check
        assert 'target_count' in check
        assert 'delta' in check
        assert 'delta_pct' in check
        assert 'status' in check


# ── Test 4: status='ok' when delta_pct < 5 ───────────────────────────────────
def test_status_ok_when_delta_pct_less_than_5():
    # 2% drift: 1000 → 1020
    with _patch_two_orgs(1000, 1020):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    for check in result['checks']:
        assert check['status'] == 'ok', f"Expected ok, got {check['status']} for {check['label']}"


# ── Test 5: status='warning' when delta_pct between 5 and 20 ─────────────────
def test_status_warning_when_delta_pct_5_to_20():
    # 10% drift: 1000 → 1100
    with _patch_two_orgs(1000, 1100):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    for check in result['checks']:
        assert check['status'] == 'warning', f"Expected warning, got {check['status']} for {check['label']}"


# ── Test 6: status='critical' when delta_pct > 20 ────────────────────────────
def test_status_critical_when_delta_pct_greater_than_20():
    # 50% drift: 1000 → 1500
    with _patch_two_orgs(1000, 1500):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    for check in result['checks']:
        assert check['status'] == 'critical', f"Expected critical, got {check['status']} for {check['label']}"


# ── Test 7: status='critical' when baseline > 0 and target == 0 ──────────────
def test_status_critical_when_baseline_nonzero_and_target_zero():
    with _patch_two_orgs(500, 0):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')
    for check in result['checks']:
        assert check['status'] == 'critical', f"Expected critical, got {check['status']} for {check['label']}"


# ── Test 8: per-check exception sets status='error' ──────────────────────────
def test_per_check_exception_sets_status_error():
    sf_base = MagicMock()
    sf_target = MagicMock()
    # Make sf_base raise on every query
    sf_base.query.side_effect = Exception('Connection refused')
    sf_target.query.return_value = {'totalSize': 100, 'done': True, 'records': []}

    call_counts = {'n': 0}

    def get_sf_side_effect(org):
        call_counts['n'] += 1
        if call_counts['n'] == 1:
            return sf_base
        return sf_target

    with patch('services.sandbox_drift.get_sf', side_effect=get_sf_side_effect):
        from services.sandbox_drift import run
        result = run('prod', 'sandbox')

    for check in result['checks']:
        assert check['status'] == 'error'
        assert 'error' in check
        assert check['baseline_count'] is None


# ── Test 9: GET /observe/sandbox-drift → 200 with success JSON ───────────────
def test_route_sandbox_drift_returns_200(client):
    with _patch_two_orgs(1000, 980):
        resp = client.get('/observe/sandbox-drift?baseline=prod&target=sandbox')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['data'] is not None


# ── Test 10: baseline_org and target_org appear in response data ──────────────
def test_route_returns_correct_org_names(client):
    with _patch_two_orgs(1000, 980):
        resp = client.get('/observe/sandbox-drift?baseline=prod&target=sandbox')
    payload = resp.get_json()
    data = payload['data']
    assert data['baseline_org'] == 'prod'
    assert data['target_org'] == 'sandbox'
