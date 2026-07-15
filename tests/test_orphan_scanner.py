"""Tests for services.orphan_scanner and /validation/orphans routes."""
from unittest.mock import MagicMock, patch

import pytest


def _clean_sf():
    """SF double: every COUNT() query returns zero — a clean org, no orphans."""
    sf = MagicMock()
    sf.query.return_value = {'totalSize': 0, 'records': [], 'done': True}
    return sf


def _orphans_sf(count=3):
    """SF double: COUNT() queries return `count`, sample queries return rows."""
    sf = MagicMock()

    def _query(soql):
        if 'COUNT()' in soql:
            return {'totalSize': count, 'records': [], 'done': True}
        return {'records': [{'Id': f'00X{i}'} for i in range(count)],
                'totalSize': count, 'done': True}

    sf.query.side_effect = _query
    return sf


# ── Service tests ─────────────────────────────────────────────────────────────

def test_scan_returns_list():
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        from services.orphan_scanner import scan
        result = scan('dev')
    assert isinstance(result, list)


def test_scan_has_all_six_checks():
    from services.orphan_scanner import scan, CHECKS
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        result = scan('dev')
    expected_keys = {c['key'] for c in CHECKS}
    result_keys = {r['key'] for r in result}
    assert result_keys == expected_keys
    assert len(result) == len(CHECKS)


def test_scan_item_has_required_keys():
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        from services.orphan_scanner import scan
        result = scan('dev')
    for item in result:
        assert 'key' in item
        assert 'label' in item
        assert 'description' in item
        assert 'count' in item
        assert 'status' in item
        assert 'samples' in item


def test_scan_status_ok_when_count_zero():
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        from services.orphan_scanner import scan
        result = scan('dev')
    for item in result:
        assert item['count'] == 0
        assert item['status'] == 'ok'
        assert item['samples'] == []


def test_scan_status_warning_when_count_positive():
    """A non-zero orphan count yields status='warning' and sample records."""
    with patch('services.orphan_scanner.get_sf', return_value=_orphans_sf(3)):
        from services.orphan_scanner import scan
        result = scan('dev')
    for item in result:
        assert item['count'] == 3
        assert item['status'] == 'warning'
        assert len(item['samples']) == 3


def test_scan_per_check_exception_sets_error_status():
    """If the first SF query raises, status='error' and count=0 for that check."""
    sf = MagicMock()
    call_count = {'n': 0}

    def _query(soql):
        call_count['n'] += 1
        if call_count['n'] == 1:
            raise RuntimeError('simulated SF error')
        return {'totalSize': 0, 'records': [], 'done': True}

    sf.query.side_effect = _query

    with patch('services.orphan_scanner.get_sf', return_value=sf):
        from services import orphan_scanner
        result = orphan_scanner.scan('dev')

    first = result[0]
    assert first['status'] == 'error'
    assert first['count'] == 0
    assert 'error' in first


# ── Route tests ───────────────────────────────────────────────────────────────

def test_orphans_page_returns_200(client):
    resp = client.get('/validation/orphans')
    assert resp.status_code == 200


def test_orphans_scan_api_returns_200_and_success(client):
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        resp = client.get('/api/v1/validation/orphans/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_orphans_scan_api_data_structure(client):
    with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
        resp = client.get('/api/v1/validation/orphans/scan')
    data = resp.get_json()
    assert data['success'] is True
    checks = data['data']
    assert isinstance(checks, list)
    assert len(checks) == 6
    for item in checks:
        assert 'key' in item
        assert 'label' in item
        assert 'description' in item
        assert 'count' in item
        assert 'status' in item
        assert 'samples' in item
        assert item['status'] in ('ok', 'warning', 'error')


# ── Legacy redirect ───────────────────────────────────────────────────────────

class TestValidationLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/validation/orphans/scan', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/validation/orphans/scan')

    def test_old_path_redirect_is_followable(self, client, monkeypatch):
        with patch('services.orphan_scanner.get_sf', return_value=_clean_sf()):
            resp = client.get('/validation/orphans/scan', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
