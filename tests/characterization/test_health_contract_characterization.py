"""
Characterization tests — health endpoint contract.

Pins the two required health endpoints against the Doane engineering
standard's exact contract:
- GET /api/v1/health (liveness): 200 always, body has status/service/version/
  uptime_seconds, status is literally "ok" (never "healthy"/"up").
- GET /api/v1/health/deep (readiness): body has a "mock" key and a "checks"
  dict with per-dependency status.
- Bare GET /health is deprecated and must redirect (308) to /api/v1/health,
  never serve its own body.

If one of these fails, either the endpoint's shape drifted or someone
re-introduced an unversioned health path as the primary one — both are
conformance regressions this test exists to catch.
"""
from config import Config


def test_liveness_contract_characterization(client):
    resp = client.get('/api/v1/health')
    assert resp.status_code == 200
    body = resp.get_json()
    for key in ('status', 'service', 'version', 'uptime_seconds'):
        assert key in body, f'/api/v1/health response missing required key "{key}"'
    assert body['status'] == 'ok', (
        'Liveness status must be the literal string "ok" per the standard — '
        f'got {body["status"]!r}.'
    )
    assert body['service'] == 'sf-mission-control'
    assert isinstance(body['uptime_seconds'], (int, float))


def test_liveness_has_no_dependency_signal_keys_characterization(client):
    # Liveness must never perform dependency calls -- pinning the absence of
    # dependency-shaped keys is a proxy for "no DB/SF/Conductor call happened".
    resp = client.get('/api/v1/health')
    body = resp.get_json()
    assert 'checks' not in body
    assert 'db_status' not in body


def test_readiness_contract_characterization(client):
    resp = client.get('/api/v1/health/deep')
    assert resp.status_code == 200
    body = resp.get_json()
    for key in ('status', 'service', 'version', 'uptime_seconds', 'mock', 'checks'):
        assert key in body, f'/api/v1/health/deep response missing required key "{key}"'
    assert body['status'] in ('ok', 'degraded')
    assert isinstance(body['mock'], bool)
    assert body['mock'] == Config.SHOW_MOCK
    assert 'database' in body['checks']
    assert 'status' in body['checks']['database']
    assert 'latency_ms' in body['checks']['database']


def test_bare_health_path_redirects_not_serves_characterization(client):
    resp = client.get('/health', follow_redirects=False)
    assert resp.status_code == 308, 'Bare /health is deprecated and must 308-redirect, not serve its own body.'
    assert resp.headers['Location'].endswith('/api/v1/health')
