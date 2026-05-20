"""Tests for batch requeue functionality."""
import pytest


# ── Service tests ──────────────────────────────────────────────────────────────

def test_requeue_batch_returns_dict():
    from services.error_reconciler import requeue_batch
    result = requeue_batch('batch-001', 'dev')
    assert isinstance(result, dict)


def test_requeue_batch_has_required_keys():
    from services.error_reconciler import requeue_batch
    result = requeue_batch('batch-001', 'dev')
    assert 'batch_id' in result
    assert 'status' in result
    assert 'message' in result


def test_requeue_batch_mock_returns_queued_status():
    from services.error_reconciler import requeue_batch
    result = requeue_batch('batch-abc', 'dev')
    # Mock conductor has no requeue_batch method, so falls through to mock success
    assert result['status'] == 'queued'
    assert result['batch_id'] == 'batch-abc'


def test_requeue_batch_exception_returns_error_status(monkeypatch):
    from services import error_reconciler
    import conductor_provider

    class BrokenClient:
        def requeue_batch(self, batch_id):
            raise RuntimeError('network error')

    monkeypatch.setattr(conductor_provider, 'get_conductor_client', lambda: BrokenClient())
    result = error_reconciler.requeue_batch('batch-999', 'dev')
    assert result['status'] == 'error'
    assert 'network error' in result['message']
    assert result['batch_id'] == 'batch-999'


# ── Route tests ────────────────────────────────────────────────────────────────

def test_requeue_route_success(session_client):
    resp = session_client.post(
        '/migration/errors/requeue',
        json={'batch_id': 'batch-001'},
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] is not None


def test_requeue_route_missing_batch_id(session_client):
    resp = session_client.post(
        '/migration/errors/requeue',
        json={},
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'batch_id' in data['error']


def test_requeue_route_method_not_allowed(session_client):
    resp = session_client.get('/migration/errors/requeue')
    assert resp.status_code == 405
