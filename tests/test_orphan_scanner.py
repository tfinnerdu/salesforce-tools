"""Tests for services.orphan_scanner and /validation/orphans routes."""
import pytest


# ── Service tests ─────────────────────────────────────────────────────────────

def test_scan_returns_list():
    from services.orphan_scanner import scan
    result = scan('dev')
    assert isinstance(result, list)


def test_scan_has_all_six_checks():
    from services.orphan_scanner import scan, CHECKS
    result = scan('dev')
    expected_keys = {c['key'] for c in CHECKS}
    result_keys = {r['key'] for r in result}
    assert result_keys == expected_keys
    assert len(result) == 6


def test_scan_item_has_required_keys():
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
    from services.orphan_scanner import scan
    result = scan('dev')
    for item in result:
        if item['count'] == 0 and item['status'] != 'error':
            assert item['status'] == 'ok'


def test_scan_status_warning_when_count_positive():
    from services.orphan_scanner import scan
    result = scan('dev')
    for item in result:
        if item['count'] > 0:
            assert item['status'] == 'warning'


def test_scan_samples_empty_when_count_zero():
    from services.orphan_scanner import scan
    result = scan('dev')
    for item in result:
        if item['count'] == 0 and item['status'] != 'error':
            assert item['samples'] == []


def test_scan_per_check_exception_sets_error_status(monkeypatch):
    """If the SF query raises, status='error' and count=0 for that check."""
    from sf_provider import MockSalesforce
    original_query = MockSalesforce.query

    call_count = {'n': 0}

    def failing_query(self, soql):
        call_count['n'] += 1
        if call_count['n'] == 1:
            raise RuntimeError('simulated SF error')
        return original_query(self, soql)

    monkeypatch.setattr(MockSalesforce, 'query', failing_query)

    from services import orphan_scanner
    result = orphan_scanner.scan('dev')
    # First check should be error
    first = result[0]
    assert first['status'] == 'error'
    assert first['count'] == 0
    assert 'error' in first


# ── Route tests ───────────────────────────────────────────────────────────────

def test_orphans_page_returns_200(client):
    resp = client.get('/validation/orphans')
    assert resp.status_code == 200


def test_orphans_scan_api_returns_200_and_success(client):
    resp = client.get('/validation/orphans/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_orphans_scan_api_data_structure(client):
    resp = client.get('/validation/orphans/scan')
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
