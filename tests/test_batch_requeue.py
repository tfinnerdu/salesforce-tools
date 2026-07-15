"""Tests for batch requeue functionality.

`error_reconciler.requeue_batch` no longer fabricates a success response. The
Conductor client has no batch-level requeue endpoint, so the function always
raises ``RuntimeError`` and the route surfaces that as a 500.
"""
import pytest


# ── Service tests ──────────────────────────────────────────────────────────────

def test_requeue_batch_raises_runtime_error():
    from services.error_reconciler import requeue_batch
    with pytest.raises(RuntimeError):
        requeue_batch('batch-001', 'dev')


def test_requeue_batch_error_mentions_batch_id():
    from services.error_reconciler import requeue_batch
    with pytest.raises(RuntimeError) as excinfo:
        requeue_batch('batch-abc', 'dev')
    assert 'batch-abc' in str(excinfo.value)


def test_requeue_batch_error_mentions_org():
    from services.error_reconciler import requeue_batch
    with pytest.raises(RuntimeError) as excinfo:
        requeue_batch('batch-999', 'dev')
    assert 'dev' in str(excinfo.value)


# ── Route tests ────────────────────────────────────────────────────────────────

def test_requeue_route_returns_500(session_client):
    """requeue_batch always raises, so the route returns 500 with success:False."""
    resp = session_client.post(
        '/api/v1/migration/errors/requeue',
        json={'batch_id': 'batch-001'},
        content_type='application/json',
    )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert data['error']


def test_requeue_route_missing_batch_id(session_client):
    resp = session_client.post(
        '/api/v1/migration/errors/requeue',
        json={},
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'batch_id' in data['error']


def test_requeue_route_method_not_allowed(session_client):
    resp = session_client.get('/api/v1/migration/errors/requeue')
    assert resp.status_code == 405
