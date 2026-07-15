"""Integration tests for Flask routes.

Routes that touch Salesforce or Conductor patch `get_sf` /
`get_conductor_client` in each service module the route calls, supplying a
`unittest.mock` double. See tests/test_platform_events.py for the pattern.
"""
import contextlib
from unittest.mock import MagicMock, patch

import pytest


# ── Salesforce / Conductor doubles ────────────────────────────────────────────

def _sf(query_result=None, restful_result=None):
    """A Salesforce double. `query`/`query_all` return query_result;
    `restful` returns restful_result."""
    sf = MagicMock()
    qr = query_result if query_result is not None else {
        'records': [], 'totalSize': 0, 'done': True}
    sf.query.return_value = qr
    sf.query_all.return_value = qr
    if restful_result is not None:
        sf.restful.return_value = restful_result
    return sf


def _count_sf(n=10):
    """A Salesforce double whose every COUNT() query returns totalSize=n."""
    return _sf({'records': [], 'totalSize': n, 'done': True})


def _conductor():
    """A Conductor double with batch-status and workflow-search results."""
    c = MagicMock()
    c.get_batch_status.return_value = {
        'completed': 50, 'failed': 2, 'running': 3, 'timed_out': 0,
        'queued': 5, 'total': 60,
    }
    c.search_workflows.return_value = []
    c.retry_workflow.return_value = {'workflow_id': 'wf-001', 'status_code': 200}
    return c


# ── health / root ─────────────────────────────────────────────────────────────

def test_health_legacy_path_redirects(client):
    resp = client.get('/health', follow_redirects=False)
    assert resp.status_code == 308
    assert resp.headers['Location'].endswith('/api/v1/health')


def test_health_liveness_returns_200(client):
    resp = client.get('/api/v1/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['service'] == 'sf-mission-control'
    assert data['status'] == 'ok'
    assert 'uptime_seconds' in data


def test_health_readiness_returns_200(client):
    resp = client.get('/api/v1/health/deep')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] in ('ok', 'degraded')
    assert 'mock' in data
    assert 'database' in data['checks']


def test_root_redirects_to_dashboard(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


# ── Migration pages ───────────────────────────────────────────────────────────

def test_migration_readiness_page(client):
    resp = client.get('/migration/readiness')
    assert resp.status_code == 200


def test_migration_batch_page(client):
    resp = client.get('/migration/batch')
    assert resp.status_code == 200


def test_migration_reconciler_page(client):
    resp = client.get('/migration/reconciler')
    assert resp.status_code == 200


# ── Migration API ─────────────────────────────────────────────────────────────

def test_migration_readiness_run_api(client):
    with patch('services.readiness_validator.get_sf', return_value=_count_sf(100)):
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
    with patch('services.batch_tracker.get_conductor_client', return_value=_conductor()):
        resp = client.get('/migration/batch/status?workflow_name=EDA_Person_Sync')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'status' in data['data']


def test_migration_reconciler_errors_api(client):
    with patch('services.error_reconciler.get_conductor_client', return_value=_conductor()):
        resp = client.get(
            '/migration/reconciler/errors?workflow_name=EDA_Person_Sync&hours_back=24')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


# ── Validation pages / API ────────────────────────────────────────────────────

def test_validation_duplicates_page(client):
    resp = client.get('/validation/duplicates')
    assert resp.status_code == 200


def test_validation_duplicates_scan_api(client):
    with patch('services.duplicate_radar.get_sf', return_value=_sf()):
        resp = client.post('/validation/duplicates/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'strategies' in data['data']


def test_validation_external_ids_api(client):
    with patch('services.external_id_coverage.get_sf', return_value=_count_sf(100)):
        resp = client.get('/validation/external-ids/run')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_validation_contactpoints_api(client):
    with patch('services.contactpoint_scanner.get_sf', return_value=_count_sf(10)):
        resp = client.get('/validation/contactpoints/scan')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'ContactPointEmail' in data['data']


# ── SOQL page / API ───────────────────────────────────────────────────────────

def test_soql_page(client):
    resp = client.get('/soql')
    assert resp.status_code == 200


def test_soql_run_api(client):
    sf = _sf({'records': [{'attributes': {}, 'Id': '001', 'Name': 'Acme'}],
              'totalSize': 1, 'done': True})
    with patch('services.soql_workbench.get_sf', return_value=sf):
        resp = client.post('/api/v1/soql/run',
                           json={'query': 'SELECT Id, Name FROM Account LIMIT 10'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'records' in data['data']
    assert data['data']['records'][0]['Id'] == '001'


def test_soql_run_requires_query(client):
    resp = client.post('/api/v1/soql/run', json={})
    assert resp.status_code == 400


def test_soql_objects_api(client):
    sf = _sf(restful_result={'sobjects': [
        {'name': 'Account', 'label': 'Account', 'queryable': True, 'custom': False}]})
    with patch('services.soql_workbench.get_sf', return_value=sf):
        resp = client.get('/api/v1/soql/objects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert data['data'][0]['name'] == 'Account'


def test_soql_object_fields_api(client):
    sf = _sf(restful_result={'fields': [
        {'name': 'Name', 'label': 'Name', 'type': 'string', 'nillable': False,
         'externalId': False, 'calculated': False, 'picklistValues': []}]})
    with patch('services.soql_workbench.get_sf', return_value=sf):
        resp = client.get('/api/v1/soql/objects/Account/fields')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert data['data'][0]['name'] == 'Name'


# ── Schema ────────────────────────────────────────────────────────────────────

def test_schema_crosswalk_page(client):
    resp = client.get('/schema/crosswalk')
    assert resp.status_code == 200


def test_schema_org_diff_api(client):
    diff = {
        'left_org': 'dev', 'right_org': 'prod',
        'objects': {'Account': {'total_differences': 0}},
        'run_at': '2026-05-22T00:00:00',
    }
    with patch('routes.schema.schema_diff.run_diff', return_value=diff):
        resp = client.post('/schema/org-diff/run',
                           json={'compare_org': 'prod', 'objects': ['Account']})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'objects' in data['data']


# ── Data Ops ──────────────────────────────────────────────────────────────────

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


# ── Settings ──────────────────────────────────────────────────────────────────

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
    """org test connects via get_sf; with a mocked client it reports success."""
    sf = _sf({'records': [], 'totalSize': 1, 'done': True})
    sf.sf_instance = 'na1.salesforce.com'
    with patch('routes.settings_routes.get_sf', return_value=sf):
        resp = client.get('/settings/org/dev/test')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'org' in data
    assert data['success'] is True
    assert data['record_count'] == 1


# ── Migration batch rerun ─────────────────────────────────────────────────────

def test_migration_batch_rerun_requires_ids(client):
    resp = client.post('/migration/batch/rerun', json={})
    assert resp.status_code == 400


def test_migration_batch_rerun_with_ids(client):
    with patch('services.batch_tracker.get_conductor_client', return_value=_conductor()):
        resp = client.post('/migration/batch/rerun', json={'workflow_ids': ['wf-001']})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


# ── Validation duplicates merge ───────────────────────────────────────────────

def test_validation_duplicates_merge_requires_ids(client):
    resp = client.post('/validation/duplicates/merge', json={})
    assert resp.status_code == 400


def test_validation_duplicates_merge_with_ids(client):
    sf = MagicMock()
    with patch('services.duplicate_radar.get_sf', return_value=sf):
        payload = {'master_id': '001ABC', 'victim_id': '001DEF'}
        resp = client.post('/validation/duplicates/merge', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['master_id'] == '001ABC'
