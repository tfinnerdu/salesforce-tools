"""Tests for services.join_builder.

run_join fetches SF records via a `unittest.mock` Salesforce double whose
query_all returns the records each test needs.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── Salesforce double ─────────────────────────────────────────────────────────

_SF_RECORDS = [
    {'attributes': {'type': 'Account'}, 'Id': '001000000000001',
     'SIS_ID__c': 'STU00001'},
    {'attributes': {'type': 'Account'}, 'Id': '001000000000002',
     'SIS_ID__c': 'STU00002'},
    {'attributes': {'type': 'Account'}, 'Id': '001000000000003',
     'SIS_ID__c': 'STU00003'},
]


def _join_sf(records=None):
    """SF double whose query_all returns the given account records."""
    records = _SF_RECORDS if records is None else records
    sf = MagicMock()
    sf.query_all.return_value = {
        'records': records, 'totalSize': len(records), 'done': True}
    return sf


# ── build_query ───────────────────────────────────────────────────────────────

def test_build_query_returns_all_keys():
    from services.join_builder import build_query
    result = build_query(
        sql_table='students',
        sql_fields=['sis_id', 'first_name'],
        sf_object='Account',
        sf_fields=['Id', 'SIS_ID__c', 'Name'],
        join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
    )
    assert set(result.keys()) == {'openquery_sql', 'soql', 'sql_only',
                                  'join_field_sql', 'join_field_sf'}


def test_build_query_openquery_contains_table_name():
    from services.join_builder import build_query
    result = build_query(
        sql_table='students',
        sql_fields=['sis_id'],
        sf_object='Account',
        sf_fields=['Id'],
        join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
    )
    assert 'students' in result['openquery_sql']
    assert 'Account' in result['openquery_sql']


def test_build_query_soql_contains_object():
    from services.join_builder import build_query
    result = build_query(
        sql_table='tbl',
        sql_fields=['col1'],
        sf_object='ContactPointEmail',
        sf_fields=['Id', 'EmailAddress'],
        join_mapping={'sql_field': 'col1', 'sf_field': 'Id'},
    )
    assert 'ContactPointEmail' in result['soql']
    assert 'SELECT' in result['soql']


def test_build_query_sql_only_uses_table_fields():
    from services.join_builder import build_query
    result = build_query(
        sql_table='persons',
        sql_fields=['sis_id', 'email'],
        sf_object='Account',
        sf_fields=['Id'],
        join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
    )
    assert 'persons' in result['sql_only']
    assert 'sis_id' in result['sql_only']


def test_build_query_join_fields_extracted():
    from services.join_builder import build_query
    result = build_query(
        sql_table='tbl',
        sql_fields=['x'],
        sf_object='Account',
        sf_fields=['Id'],
        join_mapping={'sql_field': 'my_sql_field', 'sf_field': 'my_sf_field'},
    )
    assert result['join_field_sql'] == 'my_sql_field'
    assert result['join_field_sf'] == 'my_sf_field'


def test_build_query_empty_fields():
    from services.join_builder import build_query
    result = build_query(
        sql_table='t',
        sql_fields=[],
        sf_object='Account',
        sf_fields=[],
        join_mapping={},
    )
    assert isinstance(result['openquery_sql'], str)
    assert isinstance(result['soql'], str)


def test_build_query_multiple_sf_fields():
    from services.join_builder import build_query
    result = build_query(
        sql_table='t',
        sql_fields=['col_a', 'col_b'],
        sf_object='Account',
        sf_fields=['Id', 'Name', 'SIS_ID__c'],
        join_mapping={'sql_field': 'col_a', 'sf_field': 'SIS_ID__c'},
    )
    assert 'SIS_ID__c' in result['soql']
    assert 'col_a' in result['sql_only']
    assert 'col_b' in result['sql_only']


def test_build_query_join_field_in_openquery_on_clause():
    from services.join_builder import build_query
    result = build_query(
        sql_table='students',
        sql_fields=['sis_id'],
        sf_object='Account',
        sf_fields=['SIS_ID__c'],
        join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
    )
    assert 'sis_id' in result['openquery_sql']
    assert 'SIS_ID__c' in result['openquery_sql']


# ── run_join ──────────────────────────────────────────────────────────────────

def test_run_join_no_conn_str_returns_hint():
    from services.join_builder import run_join
    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg:
        mock_cfg.SQLSERVER_CONN = ''
        result = run_join(
            org='dev',
            sql_query='SELECT sis_id FROM students',
            soql_query='SELECT Id FROM Account WHERE IsPersonAccount = true',
            join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
        )
    assert result['success'] is False
    assert 'hint' in result
    assert 'sf_records_fetched' in result


def test_run_join_no_conn_str_sf_records_fetched():
    from services.join_builder import run_join
    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg:
        mock_cfg.SQLSERVER_CONN = ''
        result = run_join('dev', 'SELECT x FROM t', 'SELECT Id FROM Account', {})
    assert result['sf_records_fetched'] == 3


def test_run_join_rejects_write_sql():
    """A write/DDL sql_query is rejected by the read-only guard before any DB
    call — the Join Builder only ever reads the warehouse."""
    from services.join_builder import run_join
    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg:
        mock_cfg.SQLSERVER_CONN = 'Driver=SQL Server;Server=localhost'
        result = run_join(
            org='dev',
            sql_query='DELETE FROM students',
            soql_query='SELECT Id FROM Account',
            join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
        )
    assert result['success'] is False
    assert 'only' in result['error'].lower()          # "Only SELECT / WITH…"
    assert result['sf_records_fetched'] == 3           # SF fetch still reported


def test_run_join_rejects_embedded_write():
    """A write keyword buried after a leading SELECT is also rejected."""
    from services.join_builder import run_join
    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg:
        mock_cfg.SQLSERVER_CONN = 'conn'
        result = run_join(
            'dev',
            'SELECT 1; DROP TABLE students',
            'SELECT Id FROM Account', {})
    assert result['success'] is False


def test_run_join_pyodbc_failure_returns_error():
    from services.join_builder import run_join

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.side_effect = Exception("cannot connect")

    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg, \
         patch.dict('sys.modules', {'pyodbc': mock_pyodbc}):
        mock_cfg.SQLSERVER_CONN = 'Driver=SQL Server;Server=localhost'
        result = run_join('dev', 'SELECT x FROM t', 'SELECT Id FROM Account', {})

    assert result['success'] is False
    assert 'error' in result
    assert 'hint' in result


def test_run_join_success_merges_rows():
    from services.join_builder import run_join

    mock_cursor = MagicMock()
    mock_cursor.description = [('sis_id',), ('email',)]
    mock_cursor.fetchall.return_value = [('STU00001', 'a@b.com'),
                                         ('STU00002', 'c@d.com')]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.return_value = mock_conn

    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg, \
         patch.dict('sys.modules', {'pyodbc': mock_pyodbc}):
        mock_cfg.SQLSERVER_CONN = 'Driver=SQL Server;Server=localhost'
        result = run_join(
            org='dev',
            sql_query='SELECT sis_id, email FROM students',
            soql_query='SELECT Id, SIS_ID__c FROM Account WHERE IsPersonAccount = true',
            join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
        )

    assert result['success'] is True
    assert 'rows' in result
    assert 'sf_count' in result
    assert 'sql_count' in result
    assert result['sql_count'] == 2
    assert result['sf_count'] == 3


def test_run_join_success_matched_keys():
    """SF records whose SIS_ID__c matches the sql sis_id get merged."""
    from services.join_builder import run_join

    mock_cursor = MagicMock()
    mock_cursor.description = [('sis_id',)]
    # STU00001 matches the first SF record's SIS_ID__c value.
    mock_cursor.fetchall.return_value = [('STU00001',)]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.return_value = mock_conn

    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg, \
         patch.dict('sys.modules', {'pyodbc': mock_pyodbc}):
        mock_cfg.SQLSERVER_CONN = 'conn'
        result = run_join(
            org='dev',
            sql_query='SELECT sis_id FROM students',
            soql_query='SELECT Id, SIS_ID__c FROM Account WHERE IsPersonAccount = true',
            join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
        )

    assert result['success'] is True
    joined_row = result['rows'][0]
    assert 'sis_id' in joined_row
    assert joined_row['sis_id'] == 'STU00001'
    # SF fields are prefixed with sf_; the matched record's Id comes through.
    assert any(k.startswith('sf_') for k in joined_row.keys())
    assert joined_row['sf_Id'] == '001000000000001'


def test_run_join_no_matching_keys():
    """SQL rows with no matching SF record still appear (empty SF fields)."""
    from services.join_builder import run_join

    mock_cursor = MagicMock()
    mock_cursor.description = [('sis_id',)]
    mock_cursor.fetchall.return_value = [('NOMATCH99999',)]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.return_value = mock_conn

    with patch('services.join_builder.get_sf', return_value=_join_sf()), \
         patch('services.join_builder.Config') as mock_cfg, \
         patch.dict('sys.modules', {'pyodbc': mock_pyodbc}):
        mock_cfg.SQLSERVER_CONN = 'conn'
        result = run_join(
            org='dev',
            sql_query='SELECT sis_id FROM students',
            soql_query='SELECT Id, SIS_ID__c FROM Account',
            join_mapping={'sql_field': 'sis_id', 'sf_field': 'SIS_ID__c'},
        )

    assert result['success'] is True
    assert result['joined_count'] == 1
    assert result['rows'][0]['sis_id'] == 'NOMATCH99999'
    # No matching SF record → no sf_ prefixed keys merged in.
    assert not any(k.startswith('sf_') for k in result['rows'][0].keys())
