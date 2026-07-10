"""Tests for services/preflight_checklist.py and preflight routes."""
import pytest
from unittest.mock import patch, MagicMock


# ── Service unit tests ────────────────────────────────────────────────────────

def test_ensure_table_no_error():
    """_ensure_table runs without error when DB is unavailable (graceful no-op)."""
    with patch('db.db_available', return_value=False):
        from services import preflight_checklist
        # Should not raise
        preflight_checklist._ensure_table()


def test_seed_defaults_inserts_items():
    """seed_defaults inserts DEFAULT_ITEMS rows when table is empty."""
    from services import preflight_checklist

    mock_row = {'cnt': 0}
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = mock_row

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        preflight_checklist.seed_defaults('dev')

    # Should have executed one SELECT + one INSERT per default item
    calls = mock_cur.execute.call_args_list
    assert any('SELECT COUNT' in str(c) for c in calls)
    # One INSERT per DEFAULT_ITEMS entry
    insert_calls = [c for c in calls if 'INSERT INTO preflight_items' in str(c)]
    assert len(insert_calls) == len(preflight_checklist.DEFAULT_ITEMS)


def test_seed_defaults_idempotent():
    """seed_defaults does not insert rows when items already exist."""
    from services import preflight_checklist

    mock_row = {'cnt': 5}
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = mock_row

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        preflight_checklist.seed_defaults('dev')
        preflight_checklist.seed_defaults('dev')

    calls = mock_cur.execute.call_args_list
    insert_calls = [c for c in calls if 'INSERT INTO preflight_items' in str(c)]
    assert len(insert_calls) == 0


def test_list_items_returns_list_with_category():
    """list_items returns a list of dicts each containing a 'category' key."""
    from services import preflight_checklist

    fake_rows = [
        {'id': 1, 'org': 'dev', 'category': 'Data Quality', 'label': 'SIS ID coverage',
         'description': 'desc', 'checked': False, 'sort_order': 10, 'is_default': True,
         'created_at': None, 'updated_at': None},
        {'id': 2, 'org': 'dev', 'category': 'Go-Live', 'label': 'Rollback plan',
         'description': 'desc2', 'checked': True, 'sort_order': 170, 'is_default': True,
         'created_at': None, 'updated_at': None},
    ]
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fake_rows

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.list_items('dev')

    assert isinstance(result, list)
    assert len(result) == 2
    assert 'category' in result[0]
    assert result[0]['category'] == 'Data Quality'


def test_toggle_item_changes_checked_state():
    """toggle_item returns the updated item with the new checked value."""
    from services import preflight_checklist

    updated_row = {
        'id': 1, 'org': 'dev', 'category': 'Data Quality', 'label': 'SIS ID coverage',
        'description': 'desc', 'checked': True, 'sort_order': 10, 'is_default': True,
        'created_at': None, 'updated_at': None,
    }
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = updated_row

    with patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.toggle_item(org='dev', item_id=1, checked=True)

    assert result['checked'] is True
    assert result['id'] == 1


def test_get_progress_returns_totals():
    """get_progress returns total, checked, pct, and by_category keys."""
    from services import preflight_checklist

    fake_rows = [
        {'category': 'Data Quality', 'total': 5, 'checked': 3},
        {'category': 'Go-Live', 'total': 6, 'checked': 2},
    ]
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fake_rows

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.get_progress('dev')

    assert result['total'] == 11
    assert result['checked'] == 5
    assert 'pct' in result
    assert 'by_category' in result


def test_get_progress_pct_zero_when_nothing_checked():
    """get_progress returns pct=0 when no items are checked."""
    from services import preflight_checklist

    fake_rows = [
        {'category': 'Data Quality', 'total': 5, 'checked': 0},
    ]
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fake_rows

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.get_progress('dev')

    assert result['pct'] == 0
    assert result['checked'] == 0


def test_get_progress_pct_100_when_all_checked():
    """get_progress returns pct=100 when all items are checked."""
    from services import preflight_checklist

    fake_rows = [
        {'category': 'Go-Live', 'total': 6, 'checked': 6},
    ]
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fake_rows

    with patch('db.db_available', return_value=True), \
         patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.get_progress('dev')

    assert result['pct'] == 100
    assert result['checked'] == result['total']


def test_add_item_creates_new_item():
    """add_item inserts a new custom row and returns it."""
    from services import preflight_checklist

    order_row = {'next_order': 220}
    new_item_row = {
        'id': 99, 'org': 'dev', 'category': 'Custom', 'label': 'My step',
        'description': 'do the thing', 'checked': False, 'sort_order': 220,
        'is_default': False, 'created_at': None, 'updated_at': None,
    }
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [order_row, new_item_row]

    with patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = preflight_checklist.add_item('dev', 'Custom', 'My step', 'do the thing')

    assert result['id'] == 99
    assert result['label'] == 'My step'
    assert result['is_default'] is False


# ── Route integration tests ───────────────────────────────────────────────────

def test_preflight_page_returns_200(client):
    """GET /migration/preflight returns HTTP 200."""
    resp = client.get('/migration/preflight')
    assert resp.status_code == 200


def test_preflight_items_api_returns_200(client):
    """GET /migration/preflight/items returns success=True."""
    with patch('db.db_available', return_value=False):
        resp = client.get('/migration/preflight/items')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_preflight_toggle_api_returns_200(client):
    """POST /migration/preflight/toggle with valid id returns 200."""
    updated_row = {
        'id': 1, 'org': 'dev', 'category': 'Data Quality', 'label': 'SIS ID coverage',
        'description': 'desc', 'checked': True, 'sort_order': 10, 'is_default': True,
        'created_at': None, 'updated_at': None,
    }
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = updated_row

    with patch('db.get_cursor') as mock_get_cursor:
        mock_get_cursor.return_value.__enter__ = lambda s: mock_cur
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.post(
            '/migration/preflight/toggle',
            json={'id': 1, 'checked': True},
            content_type='application/json',
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
