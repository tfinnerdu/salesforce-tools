"""Boundary tests for the real (SF_MOCK=false) Bulk API code paths.

In mock mode the import/delete/modify/reassign execute functions short-circuit
to canned results, so their real logic — record-dict assembly, Bulk API result
processing, success/error counting, error-CSV generation — never runs under the
default test config. These tests flip SF_MOCK off and inject a fake Salesforce
client so that logic is exercised deterministically without a live org.
"""
import csv
import io

import pytest

from services import data_importer, bulk_ops


# ── Fake Salesforce client + Bulk API ─────────────────────────────────────────

class _FakeBulkObject:
    """Stands in for sf.bulk.<ObjectName>; records the records it was given."""
    def __init__(self, results):
        self._results = results
        self.received = None
        self.last_op = None

    def insert(self, records, **kw):
        self.received, self.last_op = records, 'insert'
        return self._results

    def update(self, records, **kw):
        self.received, self.last_op = records, 'update'
        return self._results

    def upsert(self, records, external_id_field, **kw):
        self.received, self.last_op = records, 'upsert'
        self.ext_id = external_id_field
        return self._results

    def delete(self, records, **kw):
        self.received, self.last_op = records, 'delete'
        return self._results


class _FakeBulk:
    def __init__(self, results):
        self._obj = _FakeBulkObject(results)

    def __getattr__(self, name):
        # Any object name (sf.bulk.Account, sf.bulk.ContactPointEmail__c) → same stub
        return self._obj


class _FakeSF:
    def __init__(self, results=None, query_records=None):
        self.bulk = _FakeBulk(results or [])
        self._query_records = query_records or []

    def query_all(self, soql):
        return {'records': self._query_records}


@pytest.fixture
def live_mode(monkeypatch):
    """Disable SF_MOCK so the real code paths run."""
    monkeypatch.setattr(data_importer.Config, 'SF_MOCK', False)
    monkeypatch.setattr(bulk_ops.Config, 'SF_MOCK', False)


# ── data_importer.import_csv — real path ──────────────────────────────────────

def test_import_csv_insert_processes_results(live_mode, monkeypatch):
    results = [
        {'success': True,  'id': '001AAA', 'errors': []},
        {'success': False, 'id': '',       'errors': [
            {'statusCode': 'REQUIRED_FIELD_MISSING', 'message': 'SIS_ID__c required'}]},
    ]
    sf = _FakeSF(results=results)
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: sf)

    out = data_importer.import_csv(
        'dev', 'Account', 'Name,SIS_ID__c\nA,STU1\nB,\n',
        {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')

    assert out['total'] == 2
    assert out['success_count'] == 1
    assert out['error_count'] == 1
    assert sf.bulk._obj.last_op == 'insert'
    # Empty CSV cell becomes None in the SF record dict
    assert sf.bulk._obj.received[1]['SIS_ID__c'] is None


def test_import_csv_builds_error_csv_for_failed_rows(live_mode, monkeypatch):
    results = [
        {'success': True,  'id': '001AAA', 'errors': []},
        {'success': False, 'id': '',       'errors': [
            {'statusCode': 'DUPLICATE_VALUE', 'message': 'duplicate SIS_ID__c'}]},
    ]
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF(results=results))

    out = data_importer.import_csv(
        'dev', 'Account', 'Name,SIS_ID__c\nGood,STU1\nBad,STU2\n',
        {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')

    assert out['error_csv']
    parsed = list(csv.DictReader(io.StringIO(out['error_csv'])))
    assert len(parsed) == 1                       # only the failed row
    assert parsed[0]['Name'] == 'Bad'
    assert '_sf_error' in parsed[0]
    assert 'DUPLICATE_VALUE' in parsed[0]['_sf_error']


def test_import_csv_upsert_requires_external_id(live_mode, monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF(results=[]))
    with pytest.raises(ValueError, match='external_id_field'):
        data_importer.import_csv('dev', 'Account', 'Name\nA\n',
                                 {'Name': 'Name'}, 'upsert', external_id_field='')


def test_import_csv_upsert_passes_external_id(live_mode, monkeypatch):
    results = [{'success': True, 'id': '001AAA', 'errors': []}]
    sf = _FakeSF(results=results)
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: sf)

    data_importer.import_csv('dev', 'Account', 'SIS_ID__c\nSTU1\n',
                             {'SIS_ID__c': 'SIS_ID__c'}, 'upsert',
                             external_id_field='SIS_ID__c')
    assert sf.bulk._obj.last_op == 'upsert'
    assert sf.bulk._obj.ext_id == 'SIS_ID__c'


def test_import_csv_unknown_operation_raises(live_mode, monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF(results=[]))
    with pytest.raises(ValueError, match='Unknown operation'):
        data_importer.import_csv('dev', 'Account', 'Name\nA\n',
                                 {'Name': 'Name'}, 'frobnicate')


def test_import_csv_over_row_cap_raises(live_mode, monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF(results=[]))
    monkeypatch.setattr(data_importer, '_MAX_ROWS', 2)
    big_csv = 'Name\n' + '\n'.join(f'Row{i}' for i in range(5)) + '\n'
    with pytest.raises(ValueError, match='maximum'):
        data_importer.import_csv('dev', 'Account', big_csv, {'Name': 'Name'}, 'insert')


def test_import_csv_empty_returns_zero(live_mode, monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF(results=[]))
    out = data_importer.import_csv('dev', 'Account', '', {'Name': 'Name'}, 'insert')
    assert out['total'] == 0
    assert out['success_count'] == 0


def test_import_csv_bypass_triggers_toggled(live_mode, monkeypatch):
    """bypass_triggers must be set before the load and cleared after."""
    calls = []
    import sf_provider
    monkeypatch.setattr(sf_provider, 'set_bypass_triggers',
                        lambda sf, on: calls.append(on))
    monkeypatch.setattr(data_importer, 'get_sf',
                        lambda org: _FakeSF(results=[{'success': True, 'id': '001', 'errors': []}]))

    data_importer.import_csv('dev', 'Account', 'Name\nA\n', {'Name': 'Name'},
                             'insert', bypass_triggers=True)
    assert calls == [True, False]


# ── bulk_ops execute functions — real path ────────────────────────────────────

def test_bulk_delete_execute_no_matches_returns_zero(live_mode, monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id = null')
    assert out == {'deleted': 0, 'errors': 0}


def test_bulk_delete_execute_processes_results(live_mode, monkeypatch):
    sf = _FakeSF(
        results=[{'success': True}, {'success': False}],
        query_records=[{'Id': '001AAA'}, {'Id': '001BBB'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id != null')
    assert out['deleted'] == 1
    assert out['errors'] == 1
    assert out['total'] == 2
    assert sf.bulk._obj.last_op == 'delete'


def test_bulk_modify_execute_processes_results(live_mode, monkeypatch):
    sf = _FakeSF(
        results=[{'success': True}, {'success': True}],
        query_records=[{'Id': '001AAA'}, {'Id': '001BBB'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id != null', {'Name': 'X'})
    assert out['updated'] == 2
    assert out['errors'] == 0
    # The field update is merged into every record dict
    assert all(r.get('Name') == 'X' for r in sf.bulk._obj.received)


def test_bulk_modify_execute_no_matches_returns_zero(live_mode, monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id = null', {'Name': 'X'})
    assert out == {'updated': 0, 'errors': 0}


def test_bulk_reassign_execute_processes_results(live_mode, monkeypatch):
    sf = _FakeSF(
        results=[{'success': True}],
        query_records=[{'Id': '001AAA'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id != null', '005ZZZ')
    assert out['reassigned'] == 1
    # Every record gets the new OwnerId
    assert sf.bulk._obj.received[0]['OwnerId'] == '005ZZZ'


def test_bulk_reassign_execute_no_matches_returns_zero(live_mode, monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id = null', '005ZZZ')
    assert out == {'reassigned': 0, 'errors': 0}
