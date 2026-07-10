"""Route tests for the Data Ops tools — import, export, delete, modify, reassign.

Covers page rendering, the JSON API contract for each tool, validation of
required parameters, and the 500 error path. SF-touching routes get their
service-level `get_sf` patched with unittest.mock doubles.
"""
import io
import json

import pytest


# ── Salesforce doubles ────────────────────────────────────────────────────────

class _DescribeQuerySF:
    """SF double covering describe (restful), query, and query_all."""
    _DESCRIBE = {'fields': [
        {'name': 'Name', 'label': 'Name', 'type': 'string',
         'nillable': True, 'createable': True, 'updateable': True, 'externalId': False},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string',
         'nillable': True, 'createable': True, 'updateable': True, 'externalId': True},
    ]}
    _ROWS = [{'attributes': {'type': 'Account'}, 'Id': '001AAA', 'Name': 'Acme'}]

    def restful(self, path, **kw):
        return self._DESCRIBE

    def query(self, soql):
        return {'records': self._ROWS, 'totalSize': len(self._ROWS), 'done': True}

    def query_all(self, soql):
        return {'records': self._ROWS, 'done': True}


class _FakeBulk2Object:
    def insert(self, records=None, **kw):
        return self._job(len(records))

    def update(self, records=None, **kw):
        return self._job(len(records))

    def delete(self, csv_file=None, **kw):
        import csv as _csv
        with open(csv_file, newline='') as fh:
            rows = list(_csv.reader(fh))
        return self._job(len(rows) - 1)

    def get_failed_records(self, job_id, file=None):
        return ''

    @staticmethod
    def _job(total):
        return [{'numberRecordsTotal': total, 'numberRecordsProcessed': total,
                 'numberRecordsFailed': 0, 'job_id': 'JOB1'}]


class _FakeBulk2:
    def __getattr__(self, name):
        return _FakeBulk2Object()


class _BulkSF(_DescribeQuerySF):
    """Adds a bulk2 stub to the describe/query double."""
    bulk2 = _FakeBulk2()


@pytest.fixture(autouse=True)
def patch_sf(monkeypatch):
    """Patch get_sf in every Data Ops service so routes never hit a live org."""
    from services import data_importer, bulk_ops
    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _BulkSF())
    monkeypatch.setattr(bulk_ops, 'get_sf', lambda org: _BulkSF())


# ── Page routes ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('path', [
    '/data-ops/import', '/data-ops/export', '/data-ops/delete',
    '/data-ops/modify', '/data-ops/reassign', '/data-ops/tune',
    '/data-ops/match', '/data-ops/convert',
])
def test_tool_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_convert_page_is_marked_not_implemented(client):
    """The Convert tab is an intentional stub — the page must say so."""
    resp = client.get('/data-ops/convert')
    assert resp.status_code == 200
    assert b'Not Implemented' in resp.data or b'not currently implemented' in resp.data.lower()


def test_data_ops_index_redirects_to_import(client):
    resp = client.get('/data-ops/')
    assert resp.status_code == 302
    assert 'import' in resp.headers['Location']


# ── Import: fields ────────────────────────────────────────────────────────────

def test_import_fields_returns_field_list(client):
    resp = client.post('/data-ops/import/fields', json={'object': 'Account'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert isinstance(body['data'], list)
    assert len(body['data']) >= 1


def test_import_fields_missing_object_returns_400(client):
    resp = client.post('/data-ops/import/fields', json={})
    assert resp.status_code == 400


# ── Import: validate ──────────────────────────────────────────────────────────

def _csv_upload(content='Name,SIS_ID__c\nAlice,STU1\nBob,STU2\n'):
    return (io.BytesIO(content.encode('utf-8')), 'test.csv')


def test_import_validate_returns_summary(client):
    resp = client.post('/data-ops/import/validate', data={
        'object': 'Account',
        'operation': 'insert',
        'field_mapping': json.dumps({'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}),
        'csv_file': _csv_upload(),
    }, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['total_rows'] == 2


def test_import_validate_missing_file_returns_400(client):
    resp = client.post('/data-ops/import/validate', data={
        'object': 'Account', 'field_mapping': '{}',
    }, content_type='multipart/form-data')
    assert resp.status_code == 400


# ── Import: execute ───────────────────────────────────────────────────────────

def test_import_execute_returns_results(client):
    resp = client.post('/data-ops/import/execute', data={
        'object': 'Account',
        'operation': 'insert',
        'field_mapping': json.dumps({'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}),
        'csv_file': _csv_upload(),
    }, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'success_count' in body['data']
    assert 'error_count' in body['data']


def test_import_download_errors_returns_csv(client):
    resp = client.post('/data-ops/import/download-errors', data={
        'error_csv': 'Name,_sf_error\nBad,REQUIRED_FIELD_MISSING\n',
        'filename': 'errs.csv',
    })
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type
    assert b'_sf_error' in resp.data


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_preview_returns_rows(client):
    resp = client.post('/data-ops/delete/preview',
                       json={'object': 'Account', 'where_clause': 'SIS_ID__c = null'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_delete_preview_missing_params_returns_400(client):
    resp = client.post('/data-ops/delete/preview', json={'object': 'Account'})
    assert resp.status_code == 400


def test_delete_execute_returns_counts(client):
    resp = client.post('/data-ops/delete/execute',
                       json={'object': 'Account', 'where_clause': 'Id != null'})
    assert resp.status_code == 200
    assert 'deleted' in resp.get_json()['data']


# ── Modify ────────────────────────────────────────────────────────────────────

def test_modify_preview_returns_rows(client):
    resp = client.post('/data-ops/modify/preview',
                       json={'object': 'Account', 'where_clause': 'Id != null', 'field': 'Name'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_modify_execute_returns_counts(client):
    resp = client.post('/data-ops/modify/execute', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'field_updates': {'Name': 'Updated'},
    })
    assert resp.status_code == 200
    assert 'updated' in resp.get_json()['data']


def test_modify_execute_missing_updates_returns_400(client):
    resp = client.post('/data-ops/modify/execute',
                       json={'object': 'Account', 'where_clause': 'Id != null'})
    assert resp.status_code == 400


# ── Reassign ──────────────────────────────────────────────────────────────────

def test_reassign_users_search(client):
    resp = client.get('/data-ops/reassign/users?q=')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_reassign_preview_returns_rows(client):
    resp = client.post('/data-ops/reassign/preview',
                       json={'object': 'Account', 'where_clause': 'Id != null'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_reassign_execute_returns_counts(client):
    resp = client.post('/data-ops/reassign/execute', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'new_owner_id': '005000000000000001',
    })
    assert resp.status_code == 200
    assert 'reassigned' in resp.get_json()['data']


def test_reassign_execute_missing_owner_returns_400(client):
    resp = client.post('/data-ops/reassign/execute',
                       json={'object': 'Account', 'where_clause': 'Id != null'})
    assert resp.status_code == 400


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_run_returns_csv_download(client):
    resp = client.post('/data-ops/export/run',
                       json={'soql': 'SELECT Id, Name FROM Account LIMIT 3', 'filename': 'x.csv'})
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type
    assert 'attachment' in resp.headers.get('Content-Disposition', '')


def test_export_run_accepts_form_post(client):
    resp = client.post('/data-ops/export/run', data={
        'soql': 'SELECT Id FROM Account LIMIT 2', 'filename': 'y.csv', 'all_pages': 'false',
    })
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type


def test_export_run_missing_soql_returns_400(client):
    resp = client.post('/data-ops/export/run', json={})
    assert resp.status_code == 400


# ── Error paths — every route's except branch returns a 500 envelope ──────────

def _boom(*a, **kw):
    raise RuntimeError('service down')


@pytest.mark.parametrize('path,payload,module,func', [
    ('/data-ops/import/fields',     {'object': 'Account'},
     'services.data_importer', 'get_object_fields'),
    ('/data-ops/delete/preview',    {'object': 'Account', 'where_clause': 'Id != null'},
     'services.bulk_ops', 'bulk_delete_preview'),
    ('/data-ops/delete/execute',    {'object': 'Account', 'where_clause': 'Id != null'},
     'services.bulk_ops', 'bulk_delete_execute'),
    ('/data-ops/modify/preview',    {'object': 'Account', 'where_clause': 'Id != null', 'field': 'Name'},
     'services.bulk_ops', 'bulk_modify_preview'),
    ('/data-ops/modify/execute',    {'object': 'Account', 'where_clause': 'Id != null',
                                     'field_updates': {'Name': 'X'}},
     'services.bulk_ops', 'bulk_modify_execute'),
    ('/data-ops/reassign/preview',  {'object': 'Account', 'where_clause': 'Id != null'},
     'services.bulk_ops', 'bulk_reassign_preview'),
    ('/data-ops/reassign/execute',  {'object': 'Account', 'where_clause': 'Id != null',
                                     'new_owner_id': '005000000000000001'},
     'services.bulk_ops', 'bulk_reassign_execute'),
    ('/data-ops/export/run',        {'soql': 'SELECT Id FROM Account'},
     'services.bulk_ops', 'export_to_csv'),
])
def test_json_route_error_returns_500(client, monkeypatch, path, payload, module, func):
    import importlib
    monkeypatch.setattr(importlib.import_module(module), func, _boom)
    resp = client.post(path, json=payload)
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False


def test_reassign_users_error_returns_500(client, monkeypatch):
    import services.bulk_ops as bo
    monkeypatch.setattr(bo, 'search_users', _boom)
    resp = client.get('/data-ops/reassign/users?q=x')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False


def test_import_validate_error_returns_500(client, monkeypatch):
    import services.data_importer as di
    monkeypatch.setattr(di, 'validate_csv', _boom)
    resp = client.post('/data-ops/import/validate', data={
        'object': 'Account', 'operation': 'insert', 'field_mapping': '{}',
        'csv_file': _csv_upload(),
    }, content_type='multipart/form-data')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False


def test_import_execute_error_returns_500(client, monkeypatch):
    import services.data_importer as di
    monkeypatch.setattr(di, 'import_csv', _boom)
    resp = client.post('/data-ops/import/execute', data={
        'object': 'Account', 'operation': 'insert', 'field_mapping': '{}',
        'csv_file': _csv_upload(),
    }, content_type='multipart/form-data')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
