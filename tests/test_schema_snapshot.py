"""Tests for services.schema_snapshot and /schema/snapshots routes."""
import json
from unittest.mock import MagicMock, patch

import pytest


# A describe payload with enough fields to exercise take_snapshot's mapping.
_ACCOUNT_DESCRIBE = {
    'name': 'Account',
    'fields': [
        {'name': 'Id', 'label': 'Account ID', 'type': 'id', 'length': 18,
         'nillable': False, 'defaultedOnCreate': True, 'unique': False,
         'externalId': False, 'custom': False},
        {'name': 'Name', 'label': 'Account Name', 'type': 'string', 'length': 255,
         'nillable': False, 'defaultedOnCreate': False, 'unique': False,
         'externalId': False, 'custom': False},
        {'name': 'CreatedDate', 'label': 'Created Date', 'type': 'datetime', 'length': 0,
         'nillable': False, 'defaultedOnCreate': True, 'unique': False,
         'externalId': False, 'custom': False},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string', 'length': 40,
         'nillable': True, 'defaultedOnCreate': False, 'unique': True,
         'externalId': True, 'custom': True},
        {'name': 'Ethos_Guid__c', 'label': 'Ethos GUID', 'type': 'string', 'length': 40,
         'nillable': True, 'defaultedOnCreate': False, 'unique': True,
         'externalId': True, 'custom': True},
    ],
}


def _fake_sf(describe=None):
    """A Salesforce double whose <object>.describe() returns the given payload."""
    desc = describe if describe is not None else _ACCOUNT_DESCRIBE
    sf = MagicMock()
    sf.Account.describe.return_value = desc
    # getattr(sf, <sobject>).describe() — MagicMock auto-creates attributes; set a
    # describe() on the generic case too.
    sf.describe.return_value = desc
    return sf


def _db_mock(fetchone=None, fetchall=None):
    """A psycopg2-style connection mock for the db.get_cursor() contract."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    if fetchone is not None:
        mock_cur.fetchone.return_value = fetchone
    if fetchall is not None:
        mock_cur.fetchall.return_value = fetchall
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = False
    return mock_conn, mock_cur


# ── Service tests ─────────────────────────────────────────────────────────────

def test_take_snapshot_returns_expected_keys():
    """take_snapshot returns the snapshot summary dict (no DB → id 0)."""
    with patch('services.schema_snapshot.get_sf', return_value=_fake_sf()), \
         patch('services.schema_snapshot.db_available', return_value=False):
        from services import schema_snapshot
        result = schema_snapshot.take_snapshot(org='dev', sobject='Account')
    assert 'id' in result
    assert 'org' in result
    assert 'sobject' in result
    assert 'label' in result
    assert 'field_count' in result


def test_take_snapshot_counts_described_fields():
    """field_count reflects the number of fields in the describe payload."""
    with patch('services.schema_snapshot.get_sf', return_value=_fake_sf()), \
         patch('services.schema_snapshot.db_available', return_value=False):
        from services import schema_snapshot
        result = schema_snapshot.take_snapshot(org='dev', sobject='Account')
    assert result['field_count'] == len(_ACCOUNT_DESCRIBE['fields'])
    assert result['sobject'] == 'Account'
    assert result['org'] == 'dev'


def test_take_snapshot_persists_to_db_when_available():
    """When the DB is available, take_snapshot INSERTs and returns the new id."""
    mock_conn, mock_cur = _db_mock(fetchone={'id': 42})
    with patch('services.schema_snapshot.get_sf', return_value=_fake_sf()), \
         patch('services.schema_snapshot.db_available', return_value=True), \
         patch('db.psycopg2.connect', return_value=mock_conn):
        import importlib
        import db
        importlib.reload(db)
        from services import schema_snapshot
        result = schema_snapshot.take_snapshot(org='dev', sobject='Account')
    assert result['id'] == 42
    # The INSERT carries the field metadata JSON.
    insert_sql = mock_cur.execute.call_args_list[-1][0][0]
    assert 'INSERT INTO schema_snapshots' in insert_sql


def test_list_snapshots_returns_empty_list_without_db():
    with patch('services.schema_snapshot.db_available', return_value=False):
        from services import schema_snapshot
        result = schema_snapshot.list_snapshots()
    assert result == []


def test_list_snapshots_returns_rows_when_db_available():
    rows = [
        {'id': 1, 'org': 'dev', 'sobject': 'Account',
         'snapshot_label': 'snap', 'captured_at': '2026-05-01', 'size': 100},
    ]
    mock_conn, mock_cur = _db_mock(fetchall=rows)
    with patch('services.schema_snapshot.db_available', return_value=True), \
         patch('db.psycopg2.connect', return_value=mock_conn):
        import importlib
        import db
        importlib.reload(db)
        from services import schema_snapshot
        result = schema_snapshot.list_snapshots()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]['org'] == 'dev'


def test_diff_snapshots_returns_required_keys():
    """diff_snapshots compares two stored snapshots and reports added/removed/changed."""
    fields_a = [
        {'name': 'Id', 'type': 'id'},
        {'name': 'Name', 'type': 'string'},
        {'name': 'OldField__c', 'type': 'string'},
    ]
    fields_b = [
        {'name': 'Id', 'type': 'id'},
        {'name': 'Name', 'type': 'textarea'},      # changed type
        {'name': 'NewField__c', 'type': 'string'},  # added
    ]
    row_a = {'org': 'dev', 'sobject': 'Account', 'snapshot_label': 'A',
             'captured_at': '2026-05-01', 'fields_json': json.dumps(fields_a)}
    row_b = {'org': 'dev', 'sobject': 'Account', 'snapshot_label': 'B',
             'captured_at': '2026-05-02', 'fields_json': json.dumps(fields_b)}
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [row_a, row_b]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = False
    with patch('services.schema_snapshot.db_available', return_value=True), \
         patch('db.psycopg2.connect', return_value=mock_conn):
        import importlib
        import db
        importlib.reload(db)
        from services import schema_snapshot
        result = schema_snapshot.diff_snapshots(1, 2)
    assert 'added' in result
    assert 'removed' in result
    assert 'changed' in result
    assert 'summary' in result


def test_diff_snapshots_summary_counts_added_removed_changed():
    fields_a = [
        {'name': 'Id', 'type': 'id'},
        {'name': 'Name', 'type': 'string'},
        {'name': 'OldField__c', 'type': 'string'},
    ]
    fields_b = [
        {'name': 'Id', 'type': 'id'},
        {'name': 'Name', 'type': 'textarea'},
        {'name': 'NewField__c', 'type': 'string'},
    ]
    row_a = {'org': 'dev', 'sobject': 'Account', 'snapshot_label': 'A',
             'captured_at': '2026-05-01', 'fields_json': json.dumps(fields_a)}
    row_b = {'org': 'dev', 'sobject': 'Account', 'snapshot_label': 'B',
             'captured_at': '2026-05-02', 'fields_json': json.dumps(fields_b)}
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [row_a, row_b]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = False
    with patch('services.schema_snapshot.db_available', return_value=True), \
         patch('db.psycopg2.connect', return_value=mock_conn):
        import importlib
        import db
        importlib.reload(db)
        from services import schema_snapshot
        result = schema_snapshot.diff_snapshots(1, 2)
    summary = result['summary']
    assert summary['added'] == 1     # NewField__c
    assert summary['removed'] == 1   # OldField__c
    assert summary['changed'] == 1   # Name type changed
    assert result['sobject'] == 'Account'


def test_diff_snapshots_without_db_raises():
    with patch('services.schema_snapshot.db_available', return_value=False):
        from services import schema_snapshot
        with pytest.raises(RuntimeError, match='database'):
            schema_snapshot.diff_snapshots(1, 2)


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_snapshots_list_returns_200_and_success(client):
    with patch('services.schema_snapshot.db_available', return_value=False):
        resp = client.get('/api/v1/schema/snapshots/list')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] == []


def test_post_snapshots_take_returns_200_and_sobject_in_data(session_client):
    with patch('services.schema_snapshot.get_sf', return_value=_fake_sf()), \
         patch('services.schema_snapshot.db_available', return_value=False):
        resp = session_client.post(
            '/api/v1/schema/snapshots/take',
            data=json.dumps({'sobject': 'Account'}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['sobject'] == 'Account'
    assert data['data']['field_count'] == len(_ACCOUNT_DESCRIBE['fields'])


# ── Legacy redirect ──────────────────────────────────────────────────────────

class TestSchemaLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/schema/snapshots/list', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/schema/snapshots/list')

    def test_old_path_redirect_is_followable(self, client):
        with patch('services.schema_snapshot.db_available', return_value=False):
            resp = client.get('/schema/snapshots/list', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
