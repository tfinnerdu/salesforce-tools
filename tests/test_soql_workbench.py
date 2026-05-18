"""Tests for services.soql_workbench."""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


# ── cursor helper ─────────────────────────────────────────────────────────────

def _make_cursor(rows=None, one=None):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows if rows is not None else []
    mock_cur.fetchone.return_value = one

    @contextmanager
    def _cm():
        yield mock_cur

    return _cm, mock_cur


# ── _strip_attributes ─────────────────────────────────────────────────────────

def test_strip_attributes_removes_key():
    from services.soql_workbench import _strip_attributes
    records = [{'Id': '001', 'Name': 'A', 'attributes': {'type': 'Account'}}]
    result = _strip_attributes(records)
    assert result == [{'Id': '001', 'Name': 'A'}]


def test_strip_attributes_no_attributes_key():
    from services.soql_workbench import _strip_attributes
    records = [{'Id': '001', 'Name': 'B'}]
    result = _strip_attributes(records)
    assert result == [{'Id': '001', 'Name': 'B'}]


def test_strip_attributes_empty_list():
    from services.soql_workbench import _strip_attributes
    assert _strip_attributes([]) == []


def test_strip_attributes_multiple_records():
    from services.soql_workbench import _strip_attributes
    records = [
        {'Id': '001', 'attributes': {'type': 'X'}},
        {'Id': '002', 'attributes': {'type': 'Y'}},
    ]
    result = _strip_attributes(records)
    assert all('attributes' not in r for r in result)
    assert len(result) == 2


# ── run_query ─────────────────────────────────────────────────────────────────

def test_run_query_basic(mock_sf):
    from services.soql_workbench import run_query
    cm, _ = _make_cursor()
    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', cm):
        result = run_query('dev', 'SELECT Id FROM Account LIMIT 5')
    assert 'records' in result
    assert 'total_size' in result
    assert 'done' in result
    assert 'columns' in result
    assert isinstance(result['records'], list)


def test_run_query_columns_extracted(mock_sf):
    from services.soql_workbench import run_query
    cm, _ = _make_cursor()
    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', cm):
        result = run_query('dev', 'SELECT Id, Name FROM Account LIMIT 1')
    # Mock returns records with Id, Name, IsPersonAccount, etc.
    assert len(result['columns']) > 0
    assert 'Id' in result['columns']


def test_run_query_all_pages(mock_sf):
    from services.soql_workbench import run_query
    cm, _ = _make_cursor()
    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', cm):
        result = run_query('dev', 'SELECT Id FROM Account', all_pages=True)
    assert result['total_size'] > 0


def test_run_query_empty_result():
    from services.soql_workbench import run_query
    mock_sf = MagicMock()
    mock_sf.query.return_value = {'totalSize': 0, 'done': True, 'records': []}
    cm, _ = _make_cursor()
    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', cm):
        result = run_query('dev', 'SELECT Id FROM Account WHERE Name = null')
    assert result['records'] == []
    assert result['columns'] == []
    assert result['total_size'] == 0


def test_run_query_db_failure_non_fatal(mock_sf):
    from services.soql_workbench import run_query

    @contextmanager
    def _fail_cm():
        raise Exception("DB unavailable")
        yield  # pragma: no cover

    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', _fail_cm):
        result = run_query('dev', 'SELECT Id FROM Account')
    # Should still return results even if DB write fails
    assert 'records' in result


def test_run_query_with_user_key(mock_sf):
    from services.soql_workbench import run_query
    cm, mock_cur = _make_cursor()
    with patch('services.soql_workbench.get_sf', return_value=mock_sf), \
         patch('services.soql_workbench.get_cursor', cm):
        result = run_query('dev', 'SELECT Id FROM Account', user_key='user@doane.edu')
    assert 'records' in result
    mock_cur.execute.assert_called_once()


# ── list_objects ──────────────────────────────────────────────────────────────

def test_list_objects_sorted(mock_sf):
    from services.soql_workbench import list_objects
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_objects('dev')
    assert isinstance(result, list)
    names = [o['name'] for o in result]
    assert names == sorted(names)


def test_list_objects_has_required_keys(mock_sf):
    from services.soql_workbench import list_objects
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_objects('dev')
    assert len(result) > 0
    for obj in result:
        assert 'name' in obj
        assert 'label' in obj
        assert 'queryable' in obj
        assert 'custom' in obj


def test_list_objects_filters_non_queryable():
    from services.soql_workbench import list_objects
    mock_sf = MagicMock()
    mock_sf.restful.return_value = {
        'sobjects': [
            {'name': 'Account', 'label': 'Account', 'queryable': True, 'custom': False},
            {'name': 'AggregateResult', 'label': 'AggregateResult', 'queryable': False, 'custom': False},
        ]
    }
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_objects('dev')
    names = [o['name'] for o in result]
    assert 'AggregateResult' not in names
    assert 'Account' in names


# ── list_fields ───────────────────────────────────────────────────────────────

def test_list_fields_sorted(mock_sf):
    from services.soql_workbench import list_fields
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_fields('dev', 'Account')
    assert isinstance(result, list)
    names = [f['name'] for f in result]
    assert names == sorted(names)


def test_list_fields_has_required_keys(mock_sf):
    from services.soql_workbench import list_fields
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_fields('dev', 'Account')
    assert len(result) > 0
    for field in result:
        for key in ('name', 'label', 'type', 'required', 'external_id', 'formula', 'picklist_values'):
            assert key in field


def test_list_fields_required_derived_from_nillable():
    from services.soql_workbench import list_fields
    mock_sf = MagicMock()
    mock_sf.restful.return_value = {
        'fields': [
            {'name': 'Name', 'label': 'Name', 'type': 'string', 'nillable': False,
             'externalId': False, 'calculated': False, 'picklistValues': []},
        ]
    }
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_fields('dev', 'Account')
    assert result[0]['required'] is True


def test_list_fields_picklist_values_extracted():
    from services.soql_workbench import list_fields
    mock_sf = MagicMock()
    mock_sf.restful.return_value = {
        'fields': [
            {
                'name': 'Status__c', 'label': 'Status', 'type': 'picklist',
                'nillable': True, 'externalId': False, 'calculated': False,
                'picklistValues': [{'value': 'Active'}, {'value': 'Inactive'}],
            }
        ]
    }
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = list_fields('dev', 'Custom__c')
    assert result[0]['picklist_values'] == ['Active', 'Inactive']


# ── get_saved_queries ─────────────────────────────────────────────────────────

def test_get_saved_queries_returns_list():
    from services.soql_workbench import get_saved_queries
    rows = [
        MagicMock(**{'__iter__': MagicMock(return_value=iter([('id', 1), ('name', 'Q1'), ('query', 'SELECT Id FROM Account'), ('created_at', None)])),
                     'keys': MagicMock(return_value=['id', 'name', 'query', 'created_at'])}),
    ]
    # Use RealDictRow-like objects by mocking dict() conversion
    mock_row = {'id': 1, 'name': 'Q1', 'query': 'SELECT Id FROM Account', 'created_at': None}
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [mock_row]

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.soql_workbench.get_cursor', _cm):
        result = get_saved_queries('user@doane.edu')
    assert isinstance(result, list)


def test_get_saved_queries_db_failure_returns_empty():
    from services.soql_workbench import get_saved_queries

    @contextmanager
    def _fail():
        raise Exception("no db")
        yield  # pragma: no cover

    with patch('services.soql_workbench.get_cursor', _fail):
        result = get_saved_queries('user@doane.edu')
    assert result == []


# ── save_query ────────────────────────────────────────────────────────────────

def test_save_query_returns_dict():
    from services.soql_workbench import save_query
    mock_row = {'id': 1, 'name': 'My Query', 'query': 'SELECT Id FROM Account', 'created_at': None}
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = mock_row

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.soql_workbench.get_cursor', _cm):
        result = save_query('user@doane.edu', 'My Query', 'SELECT Id FROM Account')
    assert isinstance(result, dict)


def test_save_query_fetchone_none_returns_empty():
    from services.soql_workbench import save_query
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.soql_workbench.get_cursor', _cm):
        result = save_query('user@doane.edu', 'Q', 'SELECT Id FROM Account')
    assert result == {}


def test_save_query_db_failure_returns_empty():
    from services.soql_workbench import save_query

    @contextmanager
    def _fail():
        raise Exception("no db")
        yield  # pragma: no cover

    with patch('services.soql_workbench.get_cursor', _fail):
        result = save_query('user@doane.edu', 'Q', 'SELECT Id FROM Account')
    assert result == {}


# ── delete_saved_query ────────────────────────────────────────────────────────

def test_delete_saved_query_calls_execute():
    from services.soql_workbench import delete_saved_query
    mock_cur = MagicMock()

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.soql_workbench.get_cursor', _cm):
        delete_saved_query('user@doane.edu', 42)
    mock_cur.execute.assert_called_once()
    assert '42' in str(mock_cur.execute.call_args) or 42 in mock_cur.execute.call_args[0][1]


def test_delete_saved_query_db_failure_non_fatal():
    from services.soql_workbench import delete_saved_query

    @contextmanager
    def _fail():
        raise Exception("no db")
        yield  # pragma: no cover

    with patch('services.soql_workbench.get_cursor', _fail):
        delete_saved_query('user@doane.edu', 99)  # Should not raise


# ── update_record ─────────────────────────────────────────────────────────────

def test_update_record_returns_confirmation(mock_sf):
    from services.soql_workbench import update_record
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = update_record('dev', 'Account', '001abc', 'Name', 'New Name')
    assert result['updated'] is True
    assert result['record_id'] == '001abc'
    assert result['field_name'] == 'Name'
    assert result['new_value'] == 'New Name'


def test_update_record_attribute_error_non_fatal():
    from services.soql_workbench import update_record

    class _NoAttrSF:
        """SF client that raises AttributeError for every attribute access."""
        def __getattr__(self, name):
            raise AttributeError(f"no attr {name}")

    with patch('services.soql_workbench.get_sf', return_value=_NoAttrSF()):
        result = update_record('dev', 'NonExistentObject', 'id1', 'Field', 'val')
    assert result['updated'] is True  # Always returns confirmation dict


def test_update_record_unknown_object_graceful(mock_sf):
    """getattr on MockSalesforce for unknown object still returns _MockSFObject."""
    from services.soql_workbench import update_record
    # The mock SF will return a _MockSFObject for any attribute access
    with patch('services.soql_workbench.get_sf', return_value=mock_sf):
        result = update_record('dev', 'Account', 'id123', 'PersonEmail', 'x@x.com')
    assert result['updated'] is True
