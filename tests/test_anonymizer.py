"""Tests for services.anonymizer and /admin/anonymizer/* routes."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _count_sf(total):
    """SF double whose .query() returns a COUNT() result with the given totalSize."""
    sf = MagicMock()
    sf.query.return_value = {'totalSize': total, 'records': [], 'done': True}
    return sf


# ---------------------------------------------------------------------------
# Service unit tests — list_objects (pure logic, no SF)
# ---------------------------------------------------------------------------

def test_list_objects_returns_list():
    from services.anonymizer import list_objects
    result = list_objects()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_objects_has_object_and_fields_keys():
    from services.anonymizer import list_objects
    for item in list_objects():
        assert 'object' in item
        assert 'fields' in item
        assert isinstance(item['fields'], list)


def test_list_objects_includes_account():
    from services.anonymizer import list_objects
    names = [item['object'] for item in list_objects()]
    assert 'Account' in names


# ---------------------------------------------------------------------------
# Service unit tests — preview
# ---------------------------------------------------------------------------

def test_preview_returns_required_keys():
    from services.anonymizer import preview
    with patch('services.anonymizer.get_sf', return_value=_count_sf(42)):
        result = preview(org='dev', object_name='Account', field_names=['Name', 'PersonEmail'])
    for key in ('record_count', 'soql', 'object', 'fields'):
        assert key in result


def test_preview_record_count_is_int():
    from services.anonymizer import preview
    with patch('services.anonymizer.get_sf', return_value=_count_sf(7)):
        result = preview(org='dev', object_name='Account', field_names=['Name'])
    assert isinstance(result['record_count'], int)
    assert result['record_count'] == 7


def test_preview_soql_contains_object():
    from services.anonymizer import preview
    with patch('services.anonymizer.get_sf', return_value=_count_sf(0)):
        result = preview(org='dev', object_name='Account', field_names=['Name'])
    assert 'Account' in result['soql']


def test_preview_soql_contains_fields():
    from services.anonymizer import preview
    with patch('services.anonymizer.get_sf', return_value=_count_sf(0)):
        result = preview(org='dev', object_name='Account', field_names=['Name', 'PersonEmail'])
    assert 'Name' in result['soql']
    assert 'PersonEmail' in result['soql']


def test_preview_empty_fields_uses_id_fallback():
    from services.anonymizer import preview
    with patch('services.anonymizer.get_sf', return_value=_count_sf(0)):
        result = preview(org='dev', object_name='Account', field_names=[])
    assert 'Id != null' in result['soql']


def test_preview_returns_fields_list():
    from services.anonymizer import preview
    fields = ['Name', 'Phone']
    with patch('services.anonymizer.get_sf', return_value=_count_sf(0)):
        result = preview(org='dev', object_name='Account', field_names=fields)
    assert result['fields'] == fields


def test_preview_handles_query_exception():
    from services.anonymizer import preview
    mock_sf_err = MagicMock()
    mock_sf_err.query.side_effect = Exception('SF timeout')
    with patch('services.anonymizer.get_sf', return_value=mock_sf_err):
        result = preview(org='dev', object_name='Account', field_names=['Name'])
    assert result['record_count'] == 0


# ---------------------------------------------------------------------------
# Service unit tests — run
# ---------------------------------------------------------------------------

def test_run_no_pii_url_returns_stub():
    from services.anonymizer import run
    with patch('services.anonymizer.get_sf', return_value=_count_sf(5)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = ''
        result = run(org='dev', object_name='Account', field_names=['Name'], dry_run=True)
    assert result['status'] == 'stub'
    assert 'PII_SERVICE_URL' in result['message']


def test_run_stub_includes_payload():
    from services.anonymizer import run
    with patch('services.anonymizer.get_sf', return_value=_count_sf(5)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = ''
        result = run(org='dev', object_name='Account', field_names=['Name', 'Phone'], dry_run=True)
    assert 'payload' in result
    assert result['payload']['object'] == 'Account'
    assert 'Name' in result['payload']['fields']


def test_run_stub_would_affect_is_int():
    from services.anonymizer import run
    with patch('services.anonymizer.get_sf', return_value=_count_sf(11)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = ''
        result = run(org='dev', object_name='Account', field_names=['Name'], dry_run=True)
    assert isinstance(result['would_affect'], int)
    assert result['would_affect'] == 11


def test_run_dry_run_with_pii_url():
    from services.anonymizer import run
    with patch('services.anonymizer.get_sf', return_value=_count_sf(5)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = 'https://pii.example.com/scrub'
        result = run(org='dev', object_name='Account', field_names=['Name'], dry_run=True)
    assert result['status'] == 'dry_run'
    assert 'pii.example.com' in result['message']


def test_run_dry_run_includes_pii_url_in_message():
    from services.anonymizer import run
    pii_url = 'https://pii.example.com/scrub'
    with patch('services.anonymizer.get_sf', return_value=_count_sf(5)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = pii_url
        result = run(org='dev', object_name='Account', field_names=['Name'], dry_run=True)
    assert pii_url in result['message']


def test_run_live_not_wired_returns_not_wired():
    from services.anonymizer import run
    with patch('services.anonymizer.get_sf', return_value=_count_sf(5)), \
         patch('services.anonymizer.Config') as mock_cfg:
        mock_cfg.PII_SERVICE_URL = 'https://pii.example.com/scrub'
        result = run(org='dev', object_name='Account', field_names=['Name'], dry_run=False)
    assert result['status'] == 'not_wired'


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_admin_anonymizer_objects_get(client):
    resp = client.get('/admin/anonymizer/objects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert len(data['data']) > 0


def test_admin_anonymizer_objects_has_expected_keys(client):
    resp = client.get('/admin/anonymizer/objects')
    data = resp.get_json()
    for item in data['data']:
        assert 'object' in item
        assert 'fields' in item


def test_admin_anonymizer_preview_post(session_client):
    payload = {'object': 'Account', 'fields': ['Name', 'PersonEmail']}
    with patch('services.anonymizer.get_sf', return_value=_count_sf(123)):
        resp = session_client.post(
            '/admin/anonymizer/preview',
            data=json.dumps(payload),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['record_count'] == 123
    assert 'soql' in data['data']


def test_admin_anonymizer_preview_missing_object(client):
    resp = client.post(
        '/admin/anonymizer/preview',
        data=json.dumps({'fields': ['Name']}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'object' in data['error']


def test_admin_anonymizer_run_post(session_client):
    payload = {'object': 'Account', 'fields': ['Name'], 'dry_run': True}
    with patch('services.anonymizer.get_sf', return_value=_count_sf(9)):
        resp = session_client.post(
            '/admin/anonymizer/run',
            data=json.dumps(payload),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['status'] in ('stub', 'dry_run', 'not_wired')


def test_admin_anonymizer_run_missing_object(client):
    resp = client.post(
        '/admin/anonymizer/run',
        data=json.dumps({'fields': ['Name'], 'dry_run': True}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_admin_anonymizer_run_missing_fields(client):
    resp = client.post(
        '/admin/anonymizer/run',
        data=json.dumps({'object': 'Account', 'dry_run': True}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_admin_anonymizer_run_empty_fields(client):
    resp = client.post(
        '/admin/anonymizer/run',
        data=json.dumps({'object': 'Account', 'fields': [], 'dry_run': True}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_admin_anonymizer_objects_exception_returns_500(client):
    with patch('services.anonymizer.list_objects', side_effect=Exception('boom')):
        resp = client.get('/admin/anonymizer/objects')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_admin_anonymizer_preview_exception_returns_500(client):
    with patch('services.anonymizer.preview', side_effect=Exception('sf error')):
        resp = client.post(
            '/admin/anonymizer/preview',
            data=json.dumps({'object': 'Account', 'fields': ['Name']}),
            content_type='application/json',
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


def test_admin_anonymizer_run_exception_returns_500(client):
    with patch('services.anonymizer.run', side_effect=Exception('pii error')):
        resp = client.post(
            '/admin/anonymizer/run',
            data=json.dumps({'object': 'Account', 'fields': ['Name'], 'dry_run': True}),
            content_type='application/json',
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
