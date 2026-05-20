"""Tests for the Mission Control Dashboard blueprint."""
import json
from unittest.mock import patch

import pytest


# ── 1. GET /dashboard returns 200 ─────────────────────────────────────────────

def test_dashboard_index_200(client):
    resp = client.get('/dashboard')
    assert resp.status_code == 200


# ── 2. GET /dashboard/ (trailing slash) returns 200 ──────────────────────────

def test_dashboard_index_trailing_slash_200(client):
    resp = client.get('/dashboard/')
    assert resp.status_code == 200


# ── 3. GET /dashboard/summary returns 200 with success JSON ──────────────────

def test_dashboard_summary_200(client):
    with patch('db.db_available', return_value=False):
        resp = client.get('/dashboard/summary')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


# ── 4. summary response has required keys ─────────────────────────────────────

def test_dashboard_summary_has_required_keys(client):
    with patch('db.db_available', return_value=False):
        resp = client.get('/dashboard/summary')
    data = resp.get_json()
    assert 'data' in data
    payload = data['data']
    for key in ('org', 'mock', 'readiness_pct', 'preflight_pct'):
        assert key in payload, f"Missing key: {key}"


# ── 5. readiness_pct is None when DB not available ────────────────────────────

def test_dashboard_summary_readiness_none_without_db(client):
    with patch('db.db_available', return_value=False):
        resp = client.get('/dashboard/summary')
    data = resp.get_json()
    assert data['data']['readiness_pct'] is None
    assert data['data']['preflight_pct'] is None


# ── 6. GET / redirects to /dashboard (302) ───────────────────────────────────

def test_root_redirects_to_dashboard(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


# ── 7. dashboard_bp is registered in app ─────────────────────────────────────

def test_dashboard_bp_registered(app):
    blueprint_names = list(app.blueprints.keys())
    assert 'dashboard' in blueprint_names


# ── 8. "Dashboard" appears in base.html nav ───────────────────────────────────

def test_dashboard_link_in_base_html():
    import os
    base_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'base.html')
    with open(os.path.abspath(base_path)) as f:
        content = f.read()
    assert 'Dashboard' in content, "Expected 'Dashboard' nav link in base.html"
    assert '/dashboard' in content, "Expected '/dashboard' href in base.html"
