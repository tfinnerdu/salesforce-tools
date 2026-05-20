"""Tests for services.bulk_dml and related routes."""
import pytest
from unittest.mock import MagicMock, patch

from services import bulk_dml
from services.bulk_dml import MAX_RECORDS


# ── Service unit tests ────────────────────────────────────────────────────────

def test_preview_returns_expected_keys(mock_sf):
    """preview() returns dict with count, sample_ids, exceeds_limit."""
    with patch('services.bulk_dml.get_sf', return_value=mock_sf):
        result = bulk_dml.preview(org='dev', sobject='Account',
                                  where_clause='IsPersonAccount = true')
    assert 'count' in result
    assert 'sample_ids' in result
    assert 'exceeds_limit' in result
    assert 'sobject' in result
    assert 'where_clause' in result
    assert isinstance(result['sample_ids'], list)


def test_preview_exceeds_limit_false_when_within_cap(mock_sf):
    """preview() exceeds_limit=False when count is within MAX_RECORDS."""
    with patch('services.bulk_dml.get_sf', return_value=mock_sf):
        result = bulk_dml.preview(org='dev', sobject='Account',
                                  where_clause='IsPersonAccount = true')
    # MockSalesforce returns 4312 for Account queries, well within 10,000
    assert result['exceeds_limit'] is False
    assert result['count'] <= MAX_RECORDS


def test_bulk_update_dry_run_returns_dry_run_status(mock_sf):
    """bulk_update(dry_run=True) returns status='dry_run', records_updated=0."""
    with patch('services.bulk_dml.get_sf', return_value=mock_sf):
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


def test_bulk_update_mock_live_returns_ok(mock_sf):
    """bulk_update(dry_run=False) with mock SF returns status='ok', records_updated > 0."""
    with patch('services.bulk_dml.get_sf', return_value=mock_sf), \
         patch('services.bulk_dml.Config') as mock_cfg:
        mock_cfg.SF_MOCK = True
        result = bulk_dml.bulk_update(
            org='dev', sobject='Account',
            where_clause='IsPersonAccount = true',
            field='Migration_Status__c', value='Complete',
            dry_run=False,
        )
    assert result['status'] == 'ok'
    assert result['records_updated'] > 0
    assert result['dry_run'] is False
    assert result['errors'] == []


def test_bulk_update_raises_value_error_when_over_limit(mock_sf):
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
    """POST /data-ops/bulk-update/preview returns 200 with success=True."""
    resp = session_client.post(
        '/data-ops/bulk-update/preview',
        json={'sobject': 'Account', 'where_clause': 'IsPersonAccount = true'},
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'count' in data['data']


def test_post_bulk_preview_missing_sobject_returns_400(session_client):
    """POST /data-ops/bulk-update/preview without sobject returns 400."""
    resp = session_client.post(
        '/data-ops/bulk-update/preview',
        json={'where_clause': 'IsPersonAccount = true'},
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_post_bulk_execute_dry_run_returns_dry_run_status(session_client):
    """POST /data-ops/bulk-update/execute with dry_run=True returns dry_run status."""
    resp = session_client.post(
        '/data-ops/bulk-update/execute',
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
    """POST /data-ops/bulk-update/execute without field returns 400."""
    resp = session_client.post(
        '/data-ops/bulk-update/execute',
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
