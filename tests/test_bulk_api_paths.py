"""Boundary tests for the Bulk API 2.0 code paths.

These tests inject a fake Salesforce client exposing ``sf.bulk2`` so the real
record-dict assembly, bulk2 job-result aggregation, and failed-records error
CSV logic runs deterministically without a live org.
"""
import csv

import pytest

from services import data_importer, bulk_ops


# ── Fake Salesforce client + Bulk API 2.0 ─────────────────────────────────────

class _FakeBulk2Object:
    """Stands in for sf.bulk2.<ObjectName>; records what it was given."""
    def __init__(self, processed, failed, failed_csv=''):
        self._processed = processed
        self._failed = failed
        self._failed_csv = failed_csv
        self.received = None      # the records list, or delete id-rows
        self.last_op = None
        self.ext_id = None

    def _job(self, total):
        return [{
            'numberRecordsTotal': total,
            'numberRecordsProcessed': self._processed,
            'numberRecordsFailed': self._failed,
            'job_id': 'JOB1',
        }]

    def insert(self, records=None, **kw):
        self.received, self.last_op = records, 'insert'
        return self._job(len(records))

    def update(self, records=None, **kw):
        self.received, self.last_op = records, 'update'
        return self._job(len(records))

    def upsert(self, records=None, external_id_field='Id', **kw):
        self.received, self.last_op, self.ext_id = records, 'upsert', external_id_field
        return self._job(len(records))

    def delete(self, csv_file=None, **kw):
        """bulk2 delete only takes a csv_file — read it back to verify."""
        self.last_op = 'delete'
        with open(csv_file, newline='') as fh:
            rows = list(csv.reader(fh))
        self.received = rows[1:]            # data rows, minus the 'Id' header
        return self._job(len(rows) - 1)

    def get_failed_records(self, job_id, file=None):
        return self._failed_csv


class _FakeBulk2:
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return self._obj      # any object name -> the same stub


class _FakeSF:
    def __init__(self, processed=0, failed=0, failed_csv='', query_records=None):
        self.bulk2 = _FakeBulk2(_FakeBulk2Object(processed, failed, failed_csv))
        self._query_records = query_records or []

    def query_all(self, soql):
        return {'records': self._query_records}


# ── data_importer.import_csv — bulk2 path ─────────────────────────────────────

def test_import_csv_insert_aggregates_job_counts(monkeypatch):
    sf = _FakeSF(processed=2, failed=1)
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: sf)

    out = data_importer.import_csv(
        'dev', 'Account', 'Name,SIS_ID__c\nA,STU1\nB,\n',
        {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')

    assert out['total'] == 2
    assert out['success_count'] == 1          # processed 2 - failed 1
    assert out['error_count'] == 1
    assert sf.bulk2._obj.last_op == 'insert'
    # Empty CSV cell becomes None in the SF record dict
    assert sf.bulk2._obj.received[1]['SIS_ID__c'] is None


def test_import_csv_error_csv_comes_from_failed_records(monkeypatch):
    failed_csv = ('sf__Id,sf__Error,Name,SIS_ID__c\n'
                  ',DUPLICATE_VALUE: duplicate SIS_ID__c,Bad,STU2\n')
    sf = _FakeSF(processed=2, failed=1, failed_csv=failed_csv)
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: sf)

    out = data_importer.import_csv(
        'dev', 'Account', 'Name,SIS_ID__c\nGood,STU1\nBad,STU2\n',
        {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')

    assert out['error_csv'] == failed_csv.strip()        # bulk2_failed_records trims
    assert len(out['results']) == 1                      # only the failed row
    assert out['results'][0]['success'] is False
    assert 'DUPLICATE_VALUE' in out['results'][0]['errors']
    assert out['results'][0]['source']['Name'] == 'Bad'


def test_import_csv_upsert_requires_external_id(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF())
    with pytest.raises(ValueError, match='external_id_field'):
        data_importer.import_csv('dev', 'Account', 'Name\nA\n',
                                 {'Name': 'Name'}, 'upsert', external_id_field='')


def test_import_csv_upsert_passes_external_id(monkeypatch):
    sf = _FakeSF(processed=1, failed=0)
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: sf)

    data_importer.import_csv('dev', 'Account', 'SIS_ID__c\nSTU1\n',
                             {'SIS_ID__c': 'SIS_ID__c'}, 'upsert',
                             external_id_field='SIS_ID__c')
    assert sf.bulk2._obj.last_op == 'upsert'
    assert sf.bulk2._obj.ext_id == 'SIS_ID__c'


def test_import_csv_unknown_operation_raises(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF())
    with pytest.raises(ValueError, match='Unknown bulk operation'):
        data_importer.import_csv('dev', 'Account', 'Name\nA\n',
                                 {'Name': 'Name'}, 'frobnicate')


def test_import_csv_over_row_cap_raises(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF())
    monkeypatch.setattr(data_importer, '_MAX_ROWS', 2)
    big_csv = 'Name\n' + '\n'.join(f'Row{i}' for i in range(5)) + '\n'
    with pytest.raises(ValueError, match='maximum'):
        data_importer.import_csv('dev', 'Account', big_csv, {'Name': 'Name'}, 'insert')


def test_import_csv_empty_returns_zero(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _FakeSF())
    out = data_importer.import_csv('dev', 'Account', '', {'Name': 'Name'}, 'insert')
    assert out['total'] == 0
    assert out['success_count'] == 0


def test_import_csv_bypass_triggers_toggled(monkeypatch):
    """bypass_triggers must be set before the load and cleared after."""
    calls = []
    import sf_provider
    monkeypatch.setattr(sf_provider, 'set_bypass_triggers',
                        lambda sf, on: calls.append(on))
    monkeypatch.setattr(data_importer, 'get_sf',
                        lambda org: _FakeSF(processed=1, failed=0))

    data_importer.import_csv('dev', 'Account', 'Name\nA\n', {'Name': 'Name'},
                             'insert', bypass_triggers=True)
    assert calls == [True, False]


# ── bulk_ops execute functions — bulk2 path ───────────────────────────────────

def test_bulk_delete_execute_no_matches_returns_zero(monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id = null')
    assert out == {'deleted': 0, 'errors': 0}


def test_bulk_delete_execute_writes_id_csv_and_counts(monkeypatch):
    sf = _FakeSF(processed=2, failed=1,
                 query_records=[{'Id': '001AAA'}, {'Id': '001BBB'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_delete_execute('dev', 'Account', 'Id != null')
    assert out['deleted'] == 1            # processed 2 - failed 1
    assert out['errors'] == 1
    assert out['total'] == 2
    assert sf.bulk2._obj.last_op == 'delete'
    # bulk2 delete is fed a single-column Id CSV
    assert sf.bulk2._obj.received == [['001AAA'], ['001BBB']]


def test_bulk_modify_execute_processes_results(monkeypatch):
    sf = _FakeSF(processed=2, failed=0,
                 query_records=[{'Id': '001AAA'}, {'Id': '001BBB'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id != null', {'Name': 'X'})
    assert out['updated'] == 2
    assert out['errors'] == 0
    assert all(r.get('Name') == 'X' for r in sf.bulk2._obj.received)


def test_bulk_modify_execute_no_matches_returns_zero(monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_modify_execute('dev', 'Account', 'Id = null', {'Name': 'X'})
    assert out == {'updated': 0, 'errors': 0}


def test_bulk_reassign_execute_processes_results(monkeypatch):
    sf = _FakeSF(processed=1, failed=0, query_records=[{'Id': '001AAA'}])
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: sf)
    out = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id != null', '005ZZZ')
    assert out['reassigned'] == 1
    assert sf.bulk2._obj.received[0]['OwnerId'] == '005ZZZ'


def test_bulk_reassign_execute_no_matches_returns_zero(monkeypatch):
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _FakeSF(query_records=[]))
    out = bulk_ops.bulk_reassign_execute('dev', 'Account', 'Id = null', '005ZZZ')
    assert out == {'reassigned': 0, 'errors': 0}


# ── bulk2_dml helper — direct contract tests ──────────────────────────────────

class _MultiBatchSF:
    """sf.bulk2 stub returning several job-result dicts (one per batch)."""
    def __init__(self, jobs):
        self._jobs = jobs
        outer = self
        class _Obj:
            def insert(self, records=None, **kw): return outer._jobs
            def update(self, records=None, **kw): return outer._jobs
        class _B2:
            def __getattr__(self, name): return _Obj()
        self.bulk2 = _B2()


def test_bulk2_dml_aggregates_multi_batch_job_results():
    """bulk2_dml sums numberRecordsTotal/Processed/Failed across batches and
    collects every job_id — pins the simple_salesforce bulk2 result contract."""
    from sf_provider import bulk2_dml
    sf = _MultiBatchSF([
        {'numberRecordsTotal': 200, 'numberRecordsProcessed': 200,
         'numberRecordsFailed': 5, 'job_id': 'JOB_A'},
        {'numberRecordsTotal': 150, 'numberRecordsProcessed': 150,
         'numberRecordsFailed': 0, 'job_id': 'JOB_B'},
    ])
    res = bulk2_dml(sf, 'Account', 'insert', [{'Name': 'x'}])
    assert res['total'] == 350
    assert res['failed'] == 5
    assert res['succeeded'] == 345          # processed 350 - failed 5
    assert res['job_ids'] == ['JOB_A', 'JOB_B']


def test_bulk2_dml_unknown_operation_raises():
    from sf_provider import bulk2_dml
    with pytest.raises(ValueError, match='Unknown bulk operation'):
        bulk2_dml(_MultiBatchSF([]), 'Account', 'frobnicate', [{'Name': 'x'}])


def test_bulk2_dml_upsert_requires_external_id():
    from sf_provider import bulk2_dml
    with pytest.raises(ValueError, match='external_id_field'):
        bulk2_dml(_MultiBatchSF([]), 'Account', 'upsert', [{'Name': 'x'}])
