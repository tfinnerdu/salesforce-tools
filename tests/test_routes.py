"""Integration tests for Flask routes."""
import json
import pytest


def test_health_returns_200(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['service'] == 'sf-mission-control'
    assert data['status'] in ('ok', 'degraded')
    assert 'uptime_seconds' in data


def test_root_redirects_to_migration(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/migration' in resp.headers['Location']


def test_migration_readiness_page(client):
    resp = client.get('/migration/readiness')
    assert resp.status_code == 200


def test_migration_batch_page(client):
    resp = client.get('/migration/batch')
    assert resp.status_code == 200


def test_migration_reconciler_page(client):
    resp = client.get('/migration/reconciler')
    assert resp.status_code == 200


def test_migration_readiness_run_api(client):
    resp = client.post('/migration/readiness/run')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'checks' in data['data']


def test_migration_readiness_history_api(client):
    resp = client.get('/migration/readiness/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_migration_batch_status_api(client):
    resp = client.get('/migration/batch/status?workflow_name=EDA_Person_Sync')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'status' in data['data']


def test_migration_reconciler_errors_api(client):
    resp = client.get('/migration/reconciler/errors?workflow_name=EDA_Person_Sync&hours_back=24')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_validation_duplicates_page(client):
    resp = client.get('/validation/duplicates')
    assert resp.status_code == 200


def test_validation_duplicates_scan_api(client):
    resp = client.post('/validation/duplicates/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'strategies' in data['data']


def test_validation_external_ids_api(client):
    resp = client.get('/validation/external-ids/run')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_validation_contactpoints_api(client):
    resp = client.get('/validation/contactpoints/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'ContactPointEmail' in data['data']


def test_soql_page(client):
    resp = client.get('/soql')
    assert resp.status_code == 200


def test_soql_run_api(client):
    payload = {'query': 'SELECT Id, Name FROM Account LIMIT 10'}
    resp = client.post('/soql/run', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'records' in data['data']


def test_soql_run_requires_query(client):
    resp = client.post('/soql/run', json={})
    assert resp.status_code == 400


def test_soql_objects_api(client):
    resp = client.get('/soql/objects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_soql_object_fields_api(client):
    resp = client.get('/soql/objects/Account/fields')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_schema_crosswalk_page(client):
    resp = client.get('/schema/crosswalk')
    assert resp.status_code == 200


def test_schema_org_diff_api(client):
    payload = {'compare_org': 'prod', 'objects': ['Account']}
    resp = client.post('/schema/org-diff/run', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'objects' in data['data']


def test_data_ops_join_builder_page(client):
    resp = client.get('/data-ops/join')
    assert resp.status_code == 200


def test_data_ops_join_build_api(client):
    payload = {
        'sql_table': 'dbo.Students',
        'sql_fields': ['StudentId', 'FirstName'],
        'sf_object': 'Account',
        'sf_fields': ['Id', 'SIS_ID__c'],
        'join_mapping': {'sql_field': 'StudentId', 'sf_field': 'SIS_ID__c'},
    }
    resp = client.post('/data-ops/join/build', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'openquery_sql' in data['data']


def test_data_ops_join_build_requires_fields(client):
    resp = client.post('/data-ops/join/build', json={})
    assert resp.status_code == 400


def test_settings_page(client):
    resp = client.get('/settings')
    assert resp.status_code == 200


def test_settings_org_switch(client):
    resp = client.post('/settings/org/switch', json={'org': 'prod'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['active_org'] == 'prod'


def test_settings_org_test(client):
    resp = client.get('/settings/org/dev/test')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'org' in data


def test_migration_batch_rerun_requires_ids(client):
    resp = client.post('/migration/batch/rerun', json={})
    assert resp.status_code == 400


def test_migration_batch_rerun_with_ids(client):
    resp = client.post('/migration/batch/rerun', json={'workflow_ids': ['wf-001']})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_validation_duplicates_merge_requires_ids(client):
    resp = client.post('/validation/duplicates/merge', json={})
    assert resp.status_code == 400


def test_validation_duplicates_merge_with_ids(client):
    payload = {'master_id': '001ABC', 'victim_id': '001DEF'}
    resp = client.post('/validation/duplicates/merge', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
