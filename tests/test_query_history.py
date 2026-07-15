"""Tests for the Recent Queries / query history feature."""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from datetime import datetime


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_cursor(rows=None, one=None):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows if rows is not None else []
    mock_cur.fetchone.return_value = one

    @contextmanager
    def _cm():
        yield mock_cur

    return _cm, mock_cur


def _make_row(id=1, query="SELECT Id FROM Account", org="dev",
              ran_at=None, row_count=10):
    """Return a dict that behaves like a psycopg2 RealDictRow."""
    return {
        'id': id,
        'query': query,
        'org': org,
        'ran_at': ran_at or datetime(2026, 5, 20, 12, 0, 0),
        'row_count': row_count,
    }


# ── 1. get_query_history returns list when DB not available ───────────────────

def test_get_query_history_db_unavailable_returns_empty():
    from services.soql_workbench import get_query_history
    with patch('db.db_available', return_value=False):
        result = get_query_history(user_key='user1', org='dev')
    assert result == []


# ── 2. GET /soql/history returns 200 ─────────────────────────────────────────

def test_get_history_route_200(client):
    with patch('db.db_available', return_value=False):
        resp = client.get('/api/v1/soql/history')
    assert resp.status_code == 200


# ── 3. GET /soql/history response data is a list ─────────────────────────────

def test_get_history_route_data_is_list(client):
    with patch('db.db_available', return_value=False):
        resp = client.get('/api/v1/soql/history')
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data'], list)


# ── 4. DELETE /soql/history/<id> → 200 (non-existent ID is a no-op) ──────────

def test_delete_history_nonexistent_200(client):
    cm, _ = _make_cursor()
    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor', cm):
        resp = client.delete('/api/v1/soql/history/999')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True


# ── 5. get_query_history filters by org ──────────────────────────────────────

def test_get_query_history_filters_by_org():
    from services.soql_workbench import get_query_history
    row = _make_row(org='prod')
    cm, mock_cur = _make_cursor(rows=[row])
    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor', cm):
        result = get_query_history(user_key='user1', org='prod')
    # Verify the SQL was called with the correct org parameter
    call_args = mock_cur.execute.call_args
    params = call_args[0][1]
    assert params[1] == 'prod'
    assert len(result) == 1
    assert result[0]['org'] == 'prod'


# ── 6. DB unavailable → empty list without raising ────────────────────────────

def test_get_query_history_no_exception_when_db_unavailable():
    from services.soql_workbench import get_query_history
    with patch('db.db_available', return_value=False):
        try:
            result = get_query_history(user_key='x', org='dev')
        except Exception as exc:
            pytest.fail(f"get_query_history raised unexpectedly: {exc}")
    assert result == []


# ── 7. Route handles exception gracefully → 500 ───────────────────────────────

def test_get_history_route_exception_returns_500(client):
    with patch('services.soql_workbench.get_query_history',
               side_effect=RuntimeError('db exploded')):
        resp = client.get('/api/v1/soql/history')
    assert resp.status_code == 500
    body = resp.get_json()
    assert body['success'] is False
    assert 'db exploded' in body['error']


# ── 8. Delete route returns deleted: True/False in data ──────────────────────

def test_delete_history_returns_deleted_flag(client):
    cm, _ = _make_cursor()
    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor', cm):
        resp = client.delete('/api/v1/soql/history/1')
    body = resp.get_json()
    assert body['success'] is True
    assert 'deleted' in body['data']
    assert body['data']['deleted'] is True


def test_delete_history_db_unavailable_returns_deleted_false(client):
    with patch('db.db_available', return_value=False):
        resp = client.delete('/api/v1/soql/history/42')
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['deleted'] is False
