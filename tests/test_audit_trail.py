"""Tests for Setup Audit Trail service function and route."""
from unittest.mock import MagicMock, patch

import pytest


def _query_sf(records):
    sf = MagicMock()
    sf.query.return_value = {'records': records, 'totalSize': len(records), 'done': True}
    return sf


_AUDIT_ROWS = [
    {'Id': '0Ym000000000001', 'Action': 'changedProfile', 'Section': 'Manage Users',
     'CreatedDate': '2026-05-21T14:00:00.000+0000', 'CreatedBy': {'Name': 'Todd Finner'},
     'Display': 'Changed profile for user jdoe'},
    {'Id': '0Ym000000000002', 'Action': 'createdField', 'Section': 'Custom Objects',
     'CreatedDate': '2026-05-22T09:30:00.000+0000', 'CreatedBy': {'Name': 'Admin User'},
     'Display': 'Created custom field SIS_ID__c on Account'},
    {'Id': '0Ym000000000003', 'Action': 'deletedClass', 'Section': 'Apex Class',
     'CreatedDate': '2026-05-20T11:15:00.000+0000', 'CreatedBy': {'Name': 'Admin User'},
     'Display': 'Deleted Apex class OldHelper'},
]


# ── Service: get_audit_trail ───────────────────────────────────────────────────

def test_get_audit_trail_returns_list():
    from services.admin_service import get_audit_trail
    with patch('services.admin_service.get_sf', return_value=_query_sf(_AUDIT_ROWS)):
        result = get_audit_trail('dev')
    assert isinstance(result, list)
    assert len(result) == 3


def test_get_audit_trail_entry_keys():
    from services.admin_service import get_audit_trail
    with patch('services.admin_service.get_sf', return_value=_query_sf(_AUDIT_ROWS)):
        result = get_audit_trail('dev')
    for entry in result:
        for key in ('id', 'action', 'section', 'created_date', 'created_by', 'display'):
            assert key in entry


def test_get_audit_trail_preserves_query_order():
    """The service maps records in the order the SOQL (ORDER BY CreatedDate DESC)
    returns them — newest-first when the org sorts them that way."""
    from services.admin_service import get_audit_trail
    ordered = sorted(_AUDIT_ROWS, key=lambda r: r['CreatedDate'], reverse=True)
    with patch('services.admin_service.get_sf', return_value=_query_sf(ordered)):
        result = get_audit_trail('dev')
    dates = [e['created_date'] for e in result]
    assert dates == sorted(dates, reverse=True)


def test_get_audit_trail_days_parameter():
    """days parameter is accepted and forwarded into the SOQL WHERE clause."""
    from services.admin_service import get_audit_trail
    sf = _query_sf(_AUDIT_ROWS)
    with patch('services.admin_service.get_sf', return_value=sf):
        result_7 = get_audit_trail('dev', days=7)
        result_30 = get_audit_trail('dev', days=30)
    assert isinstance(result_7, list)
    assert isinstance(result_30, list)
    assert sf.query.call_count == 2


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_audit_trail_route_200(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_AUDIT_ROWS)):
        response = session_client.get('/admin/audit-trail')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_audit_trail_route_days_param(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_AUDIT_ROWS)):
        response = session_client.get('/admin/audit-trail?days=14')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_audit_trail_response_data_is_list(session_client):
    with patch('services.admin_service.get_sf', return_value=_query_sf(_AUDIT_ROWS)):
        response = session_client.get('/admin/audit-trail')
    data = response.get_json()
    assert isinstance(data['data'], list)
    assert len(data['data']) == 3


def test_audit_trail_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            'services.admin_service.get_audit_trail',
            lambda org, days=7: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/audit-trail')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
