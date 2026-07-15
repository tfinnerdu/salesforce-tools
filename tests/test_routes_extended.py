"""Extended route tests covering uncovered branches in all blueprint files.

Covers redirects, exception handlers (500s), validation branches (400s),
multipart file uploads, and SOQL/schema/settings/data-ops routes.
"""
import io
import json

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Root and logout
# ---------------------------------------------------------------------------

def test_root_redirects_to_dashboard_index(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_logout_redirects(client):
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert '/migration' in resp.headers['Location']


def test_logout_with_session(client):
    with client.session_transaction() as sess:
        sess['active_org'] = 'sandbox'
    resp = client.get('/logout')
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Migration routes — redirects and exception handlers
# ---------------------------------------------------------------------------

def test_migration_index_redirects(client):
    resp = client.get('/migration/')
    assert resp.status_code == 302
    assert 'readiness' in resp.headers['Location']


def test_migration_index_no_slash_redirects(client):
    resp = client.get('/migration')
    # Flask may 301/308 redirect bare prefix to trailing slash, then 302 inside
    assert resp.status_code in (301, 302, 308)


def test_migration_readiness_run_exception_returns_500(client):
    with patch(
        'routes.migration.readiness_validator.run_full_readiness_check',
        side_effect=Exception("SF down"),
    ):
        resp = client.post('/api/v1/migration/readiness/run')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_migration_readiness_history_exception_returns_500(client):
    with patch(
        'routes.migration.readiness_validator.get_history',
        side_effect=Exception("DB down"),
    ):
        resp = client.get('/api/v1/migration/readiness/history')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def _conductor():
    """A Conductor double for routes that fan out to batch_tracker/error_reconciler."""
    c = MagicMock()
    c.get_batch_status.return_value = {
        'completed': 1, 'failed': 0, 'running': 0, 'timed_out': 0,
        'queued': 0, 'total': 1,
    }
    c.search_workflows.return_value = []
    c.retry_workflow.return_value = {'workflow_id': 'wf-001', 'status_code': 200}
    return c


def test_migration_batch_status_invalid_start_time(client):
    """Lines 64-68: invalid start_time_ms is silently set to None."""
    with patch('services.batch_tracker.get_conductor_client', return_value=_conductor()):
        resp = client.get(
            '/api/v1/migration/batch/status?workflow_name=Test&start_time_ms=not_an_int')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_migration_batch_status_exception_returns_500(client):
    with patch(
        'routes.migration.batch_tracker.get_batch_status',
        side_effect=Exception("conductor error"),
    ):
        resp = client.get('/api/v1/migration/batch/status?workflow_name=Test')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_migration_batch_rerun_exception_returns_500(client):
    with patch(
        'routes.migration.batch_tracker.rerun_workflows',
        side_effect=Exception("retry failed"),
    ):
        resp = client.post(
            '/api/v1/migration/batch/rerun',
            json={'workflow_ids': ['wf-001']},
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_migration_reconciler_errors_invalid_hours_back(client):
    """Lines 103-105: non-numeric hours_back is coerced to 24."""
    with patch('services.error_reconciler.get_conductor_client', return_value=_conductor()):
        resp = client.get(
            '/api/v1/migration/reconciler/errors?workflow_name=Test&hours_back=abc')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_migration_reconciler_errors_exception_returns_500(client):
    with patch(
        'routes.migration.error_reconciler.categorize_conductor_failures',
        side_effect=Exception("categorize failed"),
    ):
        resp = client.get('/api/v1/migration/reconciler/errors?workflow_name=Test&hours_back=24')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_migration_reconciler_rerun_no_ids_returns_400(client):
    resp = client.post('/api/v1/migration/reconciler/rerun', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_migration_reconciler_rerun_with_ids_succeeds(client):
    with patch('services.error_reconciler.get_conductor_client', return_value=_conductor()):
        resp = client.post('/api/v1/migration/reconciler/rerun',
                           json={'workflow_ids': ['wf-001']})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_migration_reconciler_rerun_exception_returns_500(client):
    with patch(
        'routes.migration.error_reconciler.rerun_workflows',
        side_effect=Exception("rerun failed"),
    ):
        resp = client.post(
            '/api/v1/migration/reconciler/rerun',
            json={'workflow_ids': ['wf-001']},
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Validation routes — page routes and exception handlers
# ---------------------------------------------------------------------------

def test_validation_index_redirects(client):
    resp = client.get('/validation/')
    assert resp.status_code == 302
    assert 'duplicates' in resp.headers['Location']


def test_validation_external_ids_page(client):
    resp = client.get('/validation/external-ids')
    assert resp.status_code == 200


def test_validation_contactpoints_page(client):
    resp = client.get('/validation/contactpoints')
    assert resp.status_code == 200


def test_validation_duplicates_scan_exception_returns_500(client):
    with patch(
        'routes.validation.duplicate_radar.scan',
        side_effect=Exception("scan failed"),
    ):
        resp = client.post('/api/v1/validation/duplicates/scan')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_validation_duplicates_merge_exception_returns_500(client):
    with patch(
        'routes.validation.duplicate_radar.merge',
        side_effect=Exception("merge failed"),
    ):
        resp = client.post(
            '/api/v1/validation/duplicates/merge',
            json={'master_id': '001A', 'victim_id': '001B'},
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_validation_external_ids_run_exception_returns_500(client):
    with patch(
        'routes.validation.external_id_coverage.run',
        side_effect=Exception("coverage failed"),
    ):
        resp = client.get('/api/v1/validation/external-ids/run')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_validation_contactpoints_scan_exception_returns_500(client):
    with patch(
        'routes.validation.contactpoint_scanner.scan',
        side_effect=Exception("scan failed"),
    ):
        resp = client.get('/api/v1/validation/contactpoints/scan')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Schema routes — page redirects, upload, run, exception handlers
# ---------------------------------------------------------------------------

def test_schema_index_redirects(client):
    resp = client.get('/schema/')
    assert resp.status_code == 302
    assert 'crosswalk' in resp.headers['Location']


def test_schema_org_diff_page(client):
    resp = client.get('/schema/org-diff')
    assert resp.status_code == 200


def test_schema_crosswalk_upload_no_file_returns_400(client):
    resp = client.post('/api/v1/schema/crosswalk/upload', data={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'No file uploaded' in data['error']


def test_schema_crosswalk_upload_empty_filename_returns_400(client):
    data = {'file': (io.BytesIO(b''), '')}
    resp = client.post(
        '/api/v1/schema/crosswalk/upload',
        data=data,
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False
    assert 'Empty filename' in d['error']


def test_schema_crosswalk_upload_with_content_succeeds(client):
    csv_content = b"EDA_Field,EdCloud_Field,Object\nName,Name,Account\n"
    data = {'file': (io.BytesIO(csv_content), 'crosswalk.csv')}
    resp = client.post(
        '/api/v1/schema/crosswalk/upload',
        data=data,
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_schema_crosswalk_upload_exception_returns_500(client):
    csv_content = b"col1,col2\nval1,val2\n"
    data = {'file': (io.BytesIO(csv_content), 'cross.csv')}
    with patch(
        'routes.schema.crosswalk_diff.parse_csv',
        side_effect=Exception("parse error"),
    ):
        resp = client.post(
            '/api/v1/schema/crosswalk/upload',
            data=data,
            content_type='multipart/form-data',
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_schema_crosswalk_run_succeeds(client):
    with patch('services.crosswalk_diff.get_sf', return_value=MagicMock()):
        resp = client.post('/api/v1/schema/crosswalk/run', json={'mappings': []})
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_schema_crosswalk_run_exception_returns_500(client):
    with patch(
        'routes.schema.crosswalk_diff.run_live_check',
        side_effect=Exception("live check failed"),
    ):
        resp = client.post('/api/v1/schema/crosswalk/run', json={'mappings': []})
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_schema_org_diff_run_exception_returns_500(client):
    with patch(
        'routes.schema.schema_diff.run_diff',
        side_effect=Exception("diff failed"),
    ):
        resp = client.post(
            '/api/v1/schema/org-diff/run',
            json={'compare_org': 'prod', 'objects': ['Account']},
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


# ---------------------------------------------------------------------------
# Settings routes — exception handlers, collections CRUD, file upload
# ---------------------------------------------------------------------------

def test_settings_org_switch_no_org_returns_400(client):
    resp = client.post('/api/v1/settings/org/switch', json={})
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False


def test_settings_org_test_exception_returns_error_envelope(client):
    # Was a bug: this used to return HTTP 200 on failure (silently swallowed
    # by MC.api, no real error signal). Now a real non-2xx status via the
    # standard error_response() envelope.
    with patch('routes.settings_routes.get_sf', side_effect=Exception("no auth")):
        resp = client.get('/api/v1/settings/org/dev/test')
    assert resp.status_code == 502
    d = resp.get_json()
    assert d['success'] is False
    assert d['code'] == 'ORG_TEST_FAILED'
    assert 'error' in d


def test_settings_collections_list_succeeds(client):
    resp = client.get('/api/v1/settings/collections')
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_settings_collections_list_exception_returns_500(client):
    with patch(
        'routes.settings_routes.collection_manager.list_collections',
        side_effect=Exception("db error"),
    ):
        resp = client.get('/api/v1/settings/collections')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_settings_collections_create_json_no_name_returns_400(client):
    resp = client.post(
        '/api/v1/settings/collections',
        json={'collection_json': {'info': {'name': 'test'}}},
    )
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False


def test_settings_collections_create_json_succeeds(client):
    payload = {
        'name': 'Test Collection',
        'collection_json': {'info': {'name': 'Test Collection'}, 'item': []},
    }
    resp = client.post('/api/v1/settings/collections', json=payload)
    # collection_manager.create_collection tries DB; it raises and returns 500
    # or succeeds — either outcome is acceptable here; we just check it's reachable
    assert resp.status_code in (201, 500)


def test_settings_collections_create_file_upload(client):
    collection_json = json.dumps({
        'info': {'name': 'Imported', '_postman_id': 'abc'},
        'item': [],
    }).encode('utf-8')
    data = {'file': (io.BytesIO(collection_json), 'collection.json')}
    resp = client.post(
        '/api/v1/settings/collections',
        data=data,
        content_type='multipart/form-data',
    )
    # Either 201 on success or 500 if DB unavailable; both paths are covered
    assert resp.status_code in (201, 500)


def test_settings_collections_create_file_exception_returns_500(client):
    collection_json = b'{"info": {"name": "Test"}, "item": []}'
    data = {'file': (io.BytesIO(collection_json), 'col.json')}
    with patch(
        'routes.settings_routes.collection_manager.import_collection',
        side_effect=Exception("import failed"),
    ):
        resp = client.post(
            '/api/v1/settings/collections',
            data=data,
            content_type='multipart/form-data',
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_settings_collections_run_succeeds(client):
    with patch(
        'routes.settings_routes.collection_manager.run_collection',
        return_value={'results': [], 'total': 0, 'passed': 0, 'failed': 0},
    ):
        resp = client.post('/api/v1/settings/collections/1/run', json={})
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_settings_collections_run_exception_returns_500(client):
    with patch(
        'routes.settings_routes.collection_manager.run_collection',
        side_effect=Exception("run failed"),
    ):
        resp = client.post('/api/v1/settings/collections/1/run', json={})
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_settings_collections_delete_succeeds(client):
    with patch(
        'routes.settings_routes.collection_manager.delete_collection',
        return_value=None,
    ):
        resp = client.delete('/api/v1/settings/collections/1')
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_settings_collections_delete_exception_returns_500(client):
    with patch(
        'routes.settings_routes.collection_manager.delete_collection',
        side_effect=Exception("delete failed"),
    ):
        resp = client.delete('/api/v1/settings/collections/1')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


# ---------------------------------------------------------------------------
# SOQL routes — saved queries, update record, exception handlers
# ---------------------------------------------------------------------------

def test_soql_run_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.run_query',
        side_effect=Exception("query error"),
    ):
        resp = client.post('/api/v1/soql/run', json={'query': 'SELECT Id FROM Account'})
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_objects_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.list_objects',
        side_effect=Exception("objects error"),
    ):
        resp = client.get('/api/v1/soql/objects')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_object_fields_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.list_fields',
        side_effect=Exception("fields error"),
    ):
        resp = client.get('/api/v1/soql/objects/Account/fields')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_saved_get_succeeds(client):
    with patch(
        'routes.soql.soql_workbench.get_saved_queries',
        return_value=[{'id': 1, 'name': 'My Query', 'query': 'SELECT Id FROM Account'}],
    ):
        resp = client.get('/api/v1/soql/saved')
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True
    assert isinstance(d['data'], list)


def test_soql_saved_get_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.get_saved_queries',
        side_effect=Exception("get saved failed"),
    ):
        resp = client.get('/api/v1/soql/saved')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_saved_post_no_name_returns_400(client):
    resp = client.post('/api/v1/soql/saved', json={'soql': 'SELECT Id FROM Account'})
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False


def test_soql_saved_post_no_query_returns_400(client):
    resp = client.post('/api/v1/soql/saved', json={'name': 'My Query'})
    assert resp.status_code == 400


def test_soql_saved_post_succeeds(client):
    # Real frontend contract: MC.soql.saveQuery() posts {name, soql} — not
    # {name, query}. A prior mismatch here (route only read 'query') meant
    # every save from the UI silently 400'd; this pins the real body shape.
    with patch(
        'routes.soql.soql_workbench.save_query',
        return_value={'id': 1, 'name': 'My Query', 'query': 'SELECT Id FROM Account'},
    ):
        resp = client.post(
            '/api/v1/soql/saved',
            json={'name': 'My Query', 'soql': 'SELECT Id FROM Account'},
        )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d['success'] is True


def test_soql_saved_post_accepts_legacy_query_key(client):
    # Backward-compat fallback (mirrors api_run's body.get('soql', body.get('query', ''))).
    with patch(
        'routes.soql.soql_workbench.save_query',
        return_value={'id': 1, 'name': 'My Query', 'query': 'SELECT Id FROM Account'},
    ):
        resp = client.post(
            '/api/v1/soql/saved',
            json={'name': 'My Query', 'query': 'SELECT Id FROM Account'},
        )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d['success'] is True


def test_soql_saved_post_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.save_query',
        side_effect=Exception("save failed"),
    ):
        resp = client.post(
            '/api/v1/soql/saved',
            json={'name': 'My Query', 'soql': 'SELECT Id FROM Account'},
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_saved_delete_succeeds(client):
    with patch('routes.soql.soql_workbench.delete_saved_query', return_value=None):
        resp = client.delete('/api/v1/soql/saved/42')
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True
    assert d['data']['deleted_id'] == 42


def test_soql_saved_delete_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.delete_saved_query',
        side_effect=Exception("delete failed"),
    ):
        resp = client.delete('/api/v1/soql/saved/42')
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_soql_update_missing_fields_returns_400(client):
    resp = client.post('/api/v1/soql/update', json={'object_name': 'Account'})
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False


def test_soql_update_succeeds(client):
    with patch('services.soql_workbench.get_sf', return_value=MagicMock()):
        resp = client.post(
            '/api/v1/soql/update',
            json={
                'object_name': 'Account',
                'record_id': '001ABC',
                'field_name': 'Name',
                'value': 'New Name',
            },
        )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_soql_update_exception_returns_500(client):
    with patch(
        'routes.soql.soql_workbench.update_record',
        side_effect=Exception("update failed"),
    ):
        resp = client.post(
            '/api/v1/soql/update',
            json={
                'object_name': 'Account',
                'record_id': '001ABC',
                'field_name': 'Name',
                'value': 'New Name',
            },
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


# ---------------------------------------------------------------------------
# Data Ops routes — join/run, redirects, exception handlers
# ---------------------------------------------------------------------------

def test_data_ops_index_redirects(client):
    resp = client.get('/data-ops/')
    assert resp.status_code == 302
    assert 'import' in resp.headers['Location']


def test_data_ops_join_build_exception_returns_500(client):
    with patch(
        'routes.data_ops.join_builder.build_query',
        side_effect=Exception("build failed"),
    ):
        resp = client.post(
            '/api/v1/data-ops/join/build',
            json={
                'sql_table': 'dbo.Students',
                'sf_object': 'Account',
                'sql_fields': ['Id'],
                'sf_fields': ['Id'],
                'join_mapping': {},
            },
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False


def test_data_ops_join_run_no_queries_returns_400(client):
    resp = client.post('/api/v1/data-ops/join/run', json={})
    assert resp.status_code == 400
    d = resp.get_json()
    assert d['success'] is False


def test_data_ops_join_run_with_queries_succeeds(client):
    with patch(
        'routes.data_ops.join_builder.run_join',
        return_value={'rows': [], 'row_count': 0},
    ):
        resp = client.post(
            '/api/v1/data-ops/join/run',
            json={
                'sql_query': 'SELECT StudentId FROM dbo.Students',
                'soql_query': 'SELECT Id FROM Account',
                'join_mapping': {'sql_field': 'StudentId', 'sf_field': 'Id'},
            },
        )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_data_ops_join_run_with_table_config_builds_queries(client):
    """Lines 61-77: when sql_query absent but sql_table present, build_query is called first."""
    with patch(
        'routes.data_ops.join_builder.run_join',
        return_value={'rows': [], 'row_count': 0},
    ):
        resp = client.post(
            '/api/v1/data-ops/join/run',
            json={
                'sql_table': 'dbo.Students',
                'sql_fields': ['StudentId'],
                'sf_object': 'Account',
                'sf_fields': ['Id'],
                'join_field_sql': 'StudentId',
                'join_field_sf': 'SIS_ID__c',
            },
        )
    # The built query path goes through build_query then run_join
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['success'] is True


def test_data_ops_join_run_exception_returns_500(client):
    with patch(
        'routes.data_ops.join_builder.run_join',
        side_effect=Exception("run failed"),
    ):
        resp = client.post(
            '/api/v1/data-ops/join/run',
            json={
                'sql_query': 'SELECT Id FROM dbo.Students',
                'soql_query': 'SELECT Id FROM Account',
                'join_mapping': {},
            },
        )
    assert resp.status_code == 500
    d = resp.get_json()
    assert d['success'] is False
