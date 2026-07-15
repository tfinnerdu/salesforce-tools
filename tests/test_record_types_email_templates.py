"""Tests for Record Types and Email Templates service functions and routes."""
from unittest.mock import MagicMock, patch

import pytest


def _record_types_sf(rt_records, count_records=None):
    """SF double for get_record_types.

    The service first calls query_all for RecordType, then once per countable
    SobjectType for the COUNT() aggregate.
    """
    sf = MagicMock()
    results = [{'records': rt_records, 'totalSize': len(rt_records), 'done': True}]
    if count_records is not None:
        for cr in count_records:
            results.append({'records': cr, 'totalSize': len(cr), 'done': True})
    sf.query_all.side_effect = results
    return sf


def _query_all_sf(records):
    sf = MagicMock()
    sf.query_all.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_RECORD_TYPE_ROWS = [
    {'Id': '012000000000001', 'Name': 'Person Account', 'DeveloperName': 'PersonAccount',
     'SobjectType': 'Account', 'IsActive': True, 'Description': 'Ed Cloud person account'},
    {'Id': '012000000000002', 'Name': 'Business Account', 'DeveloperName': 'BusinessAccount',
     'SobjectType': 'Account', 'IsActive': True, 'Description': ''},
    {'Id': '012000000000003', 'Name': 'Prospect', 'DeveloperName': 'Prospect',
     'SobjectType': 'Opportunity', 'IsActive': False, 'Description': 'Recruiting prospect'},
]

# Account is COUNTABLE so the service issues one COUNT() query for it.
_ACCOUNT_COUNTS = [
    {'RecordTypeId': '012000000000001', 'cnt': 4312},
    {'RecordTypeId': '012000000000002', 'cnt': 88},
]
# Opportunity is COUNTABLE too.
_OPP_COUNTS = [
    {'RecordTypeId': '012000000000003', 'cnt': 17},
]


# ── Service: get_record_types ──────────────────────────────────────────────────

def test_get_record_types_returns_list():
    from services.admin_service import get_record_types
    sf = _record_types_sf(_RECORD_TYPE_ROWS, [_ACCOUNT_COUNTS, _OPP_COUNTS])
    with patch('services.admin_service.get_sf', return_value=sf):
        result = get_record_types('dev')
    assert isinstance(result, list)
    assert len(result) == 3


def test_get_record_types_required_keys():
    from services.admin_service import get_record_types
    sf = _record_types_sf(_RECORD_TYPE_ROWS, [_ACCOUNT_COUNTS, _OPP_COUNTS])
    with patch('services.admin_service.get_sf', return_value=sf):
        result = get_record_types('dev')
    for rt in result:
        for key in ('id', 'name', 'developer_name', 'sobject_type',
                    'is_active', 'record_count'):
            assert key in rt


def test_get_record_types_person_account_present():
    from services.admin_service import get_record_types
    sf = _record_types_sf(_RECORD_TYPE_ROWS, [_ACCOUNT_COUNTS, _OPP_COUNTS])
    with patch('services.admin_service.get_sf', return_value=sf):
        result = get_record_types('dev')
    by_name = {rt['name']: rt for rt in result}
    assert 'Person Account' in by_name
    # Count was populated from the COUNT() aggregate query.
    assert by_name['Person Account']['record_count'] == 4312


# ── Service: get_email_templates ───────────────────────────────────────────────

_EMAIL_TEMPLATE_ROWS = [
    {'Id': '00X000000000001', 'Name': 'Welcome Email', 'DeveloperName': 'Welcome_Email',
     'FolderId': '00l000000000001', 'FolderName': 'Recruiting', 'Subject': 'Welcome to Doane',
     'Encoding': 'UTF-8', 'IsActive': True, 'LastModifiedDate': '2026-05-01T00:00:00.000+0000',
     'LastModifiedBy': {'Name': 'Todd Finner'}},
    {'Id': '00X000000000002', 'Name': 'Old Reminder', 'DeveloperName': 'Old_Reminder',
     'FolderId': '00l000000000001', 'FolderName': 'Recruiting', 'Subject': 'Reminder',
     'Encoding': 'UTF-8', 'IsActive': False, 'LastModifiedDate': '2024-01-01T00:00:00.000+0000',
     'LastModifiedBy': {'Name': 'Admin User'}},
]


def test_get_email_templates_returns_list():
    from services.admin_service import get_email_templates
    with patch('services.admin_service.get_sf', return_value=_query_all_sf(_EMAIL_TEMPLATE_ROWS)):
        result = get_email_templates('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_email_templates_required_keys():
    from services.admin_service import get_email_templates
    with patch('services.admin_service.get_sf', return_value=_query_all_sf(_EMAIL_TEMPLATE_ROWS)):
        result = get_email_templates('dev')
    for t in result:
        for key in ('id', 'name', 'folder_name', 'subject', 'is_active'):
            assert key in t


def test_get_email_templates_inactive_present():
    from services.admin_service import get_email_templates
    with patch('services.admin_service.get_sf', return_value=_query_all_sf(_EMAIL_TEMPLATE_ROWS)):
        result = get_email_templates('dev')
    inactive = [t for t in result if not t['is_active']]
    assert len(inactive) == 1
    assert inactive[0]['name'] == 'Old Reminder'


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_record_types_route_200(session_client):
    sf = _record_types_sf(_RECORD_TYPE_ROWS, [_ACCOUNT_COUNTS, _OPP_COUNTS])
    with patch('services.admin_service.get_sf', return_value=sf):
        response = session_client.get('/api/v1/admin/record-types')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_email_templates_route_200(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_all_sf(_EMAIL_TEMPLATE_ROWS)):
        response = session_client.get('/api/v1/admin/email-templates')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_record_types_response_is_list(session_client):
    sf = _record_types_sf(_RECORD_TYPE_ROWS, [_ACCOUNT_COUNTS, _OPP_COUNTS])
    with patch('services.admin_service.get_sf', return_value=sf):
        response = session_client.get('/api/v1/admin/record-types')
    data = response.get_json()
    assert isinstance(data['data'], list)
    assert len(data['data']) == 3


def test_email_templates_response_is_list(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_all_sf(_EMAIL_TEMPLATE_ROWS)):
        response = session_client.get('/api/v1/admin/email-templates')
    data = response.get_json()
    assert isinstance(data['data'], list)
    assert len(data['data']) == 2


def test_record_types_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_record_types',
                   lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/api/v1/admin/record-types')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False


def test_email_templates_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_email_templates',
                   lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/api/v1/admin/email-templates')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
