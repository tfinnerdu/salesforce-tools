"""
Characterization tests — the three required mock/live signals.

Pins Doane's Mock/Live Signal standard: a service with a mock mode must make
that state visible in three independent, redundant places. Broader
SHOW_MOCK gating behavior (get_sf/get_conductor_client branching, no-silent-
fallback) is covered in tests/test_show_mock_gating.py; this file exists
specifically so the three-signal CONTRACT itself is pinned in one place, per
the standard's own characterization-test category list.

1. UI badge — templates/base.html's amber MOCK / green LIVE badge.
2. Health endpoint — "mock" key in GET /api/v1/health/deep.
3. Response header — X-Mock-Mode: true on every response in mock mode.

If any of these silently regresses, mock mode becomes an invisible state —
exactly the "correctness and trust hazard" the standard calls out.
"""
from pathlib import Path

from config import Config

_BASE_HTML = Path(__file__).resolve().parents[2] / 'templates' / 'base.html'


def test_mock_health_key_characterization(client, monkeypatch):
    monkeypatch.setattr(Config, 'SHOW_MOCK', True)
    resp = client.get('/api/v1/health/deep')
    assert resp.get_json()['mock'] is True

    monkeypatch.setattr(Config, 'SHOW_MOCK', False)
    resp = client.get('/api/v1/health/deep')
    assert resp.get_json()['mock'] is False


def test_mock_response_header_characterization(client, monkeypatch):
    monkeypatch.setattr(Config, 'SHOW_MOCK', True)
    resp = client.get('/api/v1/health')
    assert resp.headers.get('X-Mock-Mode') == 'true'

    monkeypatch.setattr(Config, 'SHOW_MOCK', False)
    resp = client.get('/api/v1/health')
    assert 'X-Mock-Mode' not in resp.headers


def test_navbar_badge_markup_present_characterization():
    html = _BASE_HTML.read_text()
    assert 'name="show-mock"' in html, 'Missing the show-mock meta tag JS reads for MC.isMock().'
    assert 'badge-amber' in html and 'MOCK' in html, 'Missing the amber MOCK badge.'
    assert 'badge-green' in html and 'LIVE' in html, 'Missing the green LIVE badge.'
