"""Tests for services.bulk_dml and related routes."""
import pytest
from unittest.mock import MagicMock, patch

from services import bulk_dml
from services.bulk_dml import MAX_RECORDS


def _fake_sf(count=4312, sample_ids=None, update_results=None):
    """A Salesforce double for the bulk_dml preview + bulk_update paths.

    preview() issues two query() calls: a COUNT() query (uses totalSize) and a
    LIMIT 5 sample query (uses records). bulk_update() issues a query_all() for
    the id set, then sf.bulk.<obj>.update().
    """
    sample_ids = sample_ids if sample_ids is not None else ['001A', '001B', '001C']
    sf = MagicMock()

    def _query(soql):
        if 'COUNT()' in soql:
            return {'totalSize': count, 'done': True, 'records': []}
        return {'totalSize': len(sample_ids), 'done': True,
                'records': [{'Id': i} for i in sample_ids]}

    sf.query.side_effect = _query
    sf.query_all.return_value = {
        'records': [{'Id': i} for i in sample_ids], 'done': True,
    }
    results = update_results if update_results is not None else [
        {'success': True, 'id': i, 'errors': []} for i in sample_ids
    ]
    sf.bulk.Account.update.return_value = results
    return sf


# ── Service unit tests ────────────────────────────────────────────────────────

def test_preview_returns_expected_keys():
    """preview() returns dict with count, sample_ids, exceeds_limit."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf()):
        result = bulk_dml.preview(org='dev', sobject='Account',
                                  where_clause='IsPersonAccount = true')
    assert 'count' in result
    assert 'sample_ids' in result
    assert 'exceeds_limit' in result
    assert 'sobject' in result
    assert 'where_clause' in result
    assert isinstance(result['sample_ids'], list)


def test_preview_exceeds_limit_false_when_within_cap():
    """preview() exceeds_limit=False when count is within MAX_RECORDS."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf(count=4312)):
        result = bulk_dml.preview(org='dev', sobject='Account',
                                  where_clause='IsPersonAccount = true')
    assert result['exceeds_limit'] is False
    assert result['count'] <= MAX_RECORDS


def test_bulk_update_dry_run_returns_dry_run_status():
    """bulk_update(dry_run=True) returns status='dry_run', records_updated=0."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf()):
        result = bulk_dml.bulk_update(
            org='dev', sobject='Account',
            where_clause='IsPersonAccount = true',
            field='Migration_Status__c', value='Pending',
            dry_run=True,
        )
    assert result['status'] == 'dry_run'
    assert result['records_updated'] == 0
    assert result['dry_run'] is True
    assert result['errors'] == []


def test_bulk_update_live_returns_ok():
    """bulk_update(dry_run=False) returns status='ok', records_updated > 0."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf()):
        result = bulk_dml.bulk_update(
            org='dev', sobject='Account',
            where_clause='IsPersonAccount = true',
            field='Migration_Status__c', value='Complete',
            dry_run=False,
        )
    assert result['status'] == 'ok'
    assert result['records_updated'] == 3
    assert result['dry_run'] is False
    assert result['errors'] == []


def test_bulk_update_reports_failed_records():
    """A failed bulk result is surfaced in records_failed + errors."""
    update_results = [
        {'success': True, 'id': '001A', 'errors': []},
        {'success': False, 'id': '001B',
         'errors': [{'message': 'REQUIRED_FIELD_MISSING'}]},
    ]
    sf = _fake_sf(sample_ids=['001A', '001B'], update_results=update_results)
    with patch('services.bulk_dml.get_sf', return_value=sf):
        result = bulk_dml.bulk_update(
            org='dev', sobject='Account',
            where_clause='IsPersonAccount = true',
            field='Migration_Status__c', value='Complete',
            dry_run=False,
        )
    assert result['status'] == 'partial'
    assert result['records_updated'] == 1
    assert result['records_failed'] == 1
    assert 'REQUIRED_FIELD_MISSING' in result['errors'][0]['error']


def test_bulk_update_raises_value_error_when_over_limit():
    """bulk_update raises ValueError when count > MAX_RECORDS."""
    big_count_sf = MagicMock()
    big_count_sf.query.return_value = {
        'totalSize': MAX_RECORDS + 1,
        'done': True,
        'records': [],
    }
    with patch('services.bulk_dml.get_sf', return_value=big_count_sf):
        with pytest.raises(ValueError, match='exceeding the'):
            bulk_dml.bulk_update(
                org='dev', sobject='Account',
                where_clause='IsPersonAccount = true',
                field='SomeField__c', value='X',
                dry_run=False,
            )


# ── Route integration tests ───────────────────────────────────────────────────

def test_post_bulk_preview_returns_200(session_client):
    """POST /api/v1/data-ops/bulk-update/preview returns 200 with success=True."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf()):
        resp = session_client.post(
            '/api/v1/data-ops/bulk-update/preview',
            json={'sobject': 'Account', 'where_clause': 'IsPersonAccount = true'},
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'count' in data['data']


def test_post_bulk_preview_missing_sobject_returns_400(session_client):
    """POST /api/v1/data-ops/bulk-update/preview without sobject returns 400."""
    resp = session_client.post(
        '/api/v1/data-ops/bulk-update/preview',
        json={'where_clause': 'IsPersonAccount = true'},
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_post_bulk_execute_dry_run_returns_dry_run_status(session_client):
    """POST /api/v1/data-ops/bulk-update/execute with dry_run=True returns dry_run status."""
    with patch('services.bulk_dml.get_sf', return_value=_fake_sf()):
        resp = session_client.post(
            '/api/v1/data-ops/bulk-update/execute',
            json={
                'sobject': 'Account',
                'where_clause': 'IsPersonAccount = true',
                'field': 'Migration_Status__c',
                'value': 'Pending',
                'dry_run': True,
            },
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['status'] == 'dry_run'


def test_post_bulk_execute_missing_field_returns_400(session_client):
    """POST /api/v1/data-ops/bulk-update/execute without field returns 400."""
    resp = session_client.post(
        '/api/v1/data-ops/bulk-update/execute',
        json={
            'sobject': 'Account',
            'where_clause': 'IsPersonAccount = true',
            'value': 'Pending',
            # field intentionally omitted
        },
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_get_bulk_update_page_returns_200(client):
    """GET /data-ops/bulk-update renders the page with HTTP 200."""
    resp = client.get('/data-ops/bulk-update')
    assert resp.status_code == 200
    assert b'Bulk Field Update' in resp.data
