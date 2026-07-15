"""Tests for services.perm_auditor — permission sets, users, object/field matrices."""
from unittest.mock import MagicMock, patch

import pytest

from services import perm_auditor


def _wrap(records):
    return {'records': records, 'totalSize': len(records), 'done': True}


def _routed_sf(query_map=None, query_all_map=None,
               query_default=None, query_all_default=None):
    """SF double that routes .query()/.query_all() by SOQL substring.

    *query_map* / *query_all_map* map a substring to a records list; the first
    matching substring wins. *_default* lists are used when nothing matches.
    """
    query_map = query_map or {}
    query_all_map = query_all_map or {}

    def _make(routing, default):
        def _call(soql):
            for needle, records in routing.items():
                if needle in soql:
                    return _wrap(records)
            return _wrap(default if default is not None else [])
        return _call

    sf = MagicMock()
    sf.query.side_effect = _make(query_map, query_default)
    sf.query_all.side_effect = _make(query_all_map, query_all_default)
    return sf


# ── Permission Sets ───────────────────────────────────────────────────────────

_PSET_ROWS = [
    {'Id': '0PS000000000001', 'Name': 'Recruiter', 'Label': 'Recruiter Access',
     'Description': 'Recruiting team', 'IsCustom': True, 'Type': 'Regular',
     'NamespacePrefix': None},
    {'Id': '0PS000000000002', 'Name': 'DataMigration', 'Label': 'Data Migration',
     'Description': '', 'IsCustom': True, 'Type': 'Regular', 'NamespacePrefix': None},
]
_PSET_ASSIGN_COUNTS = [
    {'PermissionSetId': '0PS000000000001', 'cnt': 12},
    {'PermissionSetId': '0PS000000000002', 'cnt': 3},
]


def _perm_sets_sf():
    # Longer/more-specific substrings must be listed first so that the
    # PermissionSetAssignment query is not matched by 'FROM PermissionSet'.
    return _routed_sf(query_all_map={
        'FROM PermissionSetAssignment': _PSET_ASSIGN_COUNTS,
        'FROM PermissionSet ': _PSET_ROWS,
    })


def test_get_permission_sets_returns_list():
    with patch('services.perm_auditor.get_sf', return_value=_perm_sets_sf()):
        psets = perm_auditor.get_permission_sets('dev')
    assert isinstance(psets, list)
    assert len(psets) == 2
    for key in ('id', 'name', 'label', 'description', 'is_custom', 'type', 'user_count'):
        assert key in psets[0]


def test_permission_set_user_count_is_int():
    with patch('services.perm_auditor.get_sf', return_value=_perm_sets_sf()):
        psets = perm_auditor.get_permission_sets('dev')
    assert all(isinstance(p['user_count'], int) for p in psets)
    by_id = {p['id']: p for p in psets}
    assert by_id['0PS000000000001']['user_count'] == 12


# ── Users ─────────────────────────────────────────────────────────────────────

_USER_ROWS = [
    {'Id': '005000000000001', 'Name': 'Alice Admin', 'Username': 'alice@doane.edu',
     'Email': 'alice@doane.edu', 'IsActive': True,
     'Profile': {'Id': '00e000000000001', 'Name': 'System Administrator'},
     'LastLoginDate': '2026-05-21T08:00:00.000+0000', 'CreatedDate': '2024-01-01T00:00:00.000+0000'},
    {'Id': '005000000000002', 'Name': 'Bob User', 'Username': 'bob@doane.edu',
     'Email': 'bob@doane.edu', 'IsActive': True,
     'Profile': {'Id': '00e000000000002', 'Name': 'Standard User'},
     'LastLoginDate': '2026-05-20T08:00:00.000+0000', 'CreatedDate': '2024-02-01T00:00:00.000+0000'},
]


def test_get_users_returns_list():
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=_USER_ROWS)):
        users = perm_auditor.get_users('dev')
    assert isinstance(users, list)
    assert len(users) == 2
    for key in ('id', 'name', 'username', 'email', 'profile_name'):
        assert key in users[0]


def test_get_users_search_filter_runs():
    """Search term is accepted and forwarded into the SOQL WHERE clause."""
    sf = _routed_sf(query_all_default=_USER_ROWS)
    with patch('services.perm_auditor.get_sf', return_value=sf):
        users = perm_auditor.get_users('dev', search='Alice')
    assert isinstance(users, list)
    issued_soql = sf.query_all.call_args[0][0]
    assert "Alice" in issued_soql


# ── User Detail ───────────────────────────────────────────────────────────────

_USER_DETAIL_ROW = [{
    'Id': '005000000000001', 'Name': 'Alice Admin', 'Username': 'alice@doane.edu',
    'Email': 'alice@doane.edu', 'IsActive': True,
    'Profile': {'Id': '00e000000000001', 'Name': 'System Administrator',
                'UserLicense': {'Name': 'Salesforce'}},
    'LastLoginDate': '2026-05-21T08:00:00.000+0000',
}]
_USER_PSET_ASSIGN = [{
    'PermissionSet': {'Id': '0PS000000000001', 'Name': 'Recruiter',
                      'Label': 'Recruiter Access', 'Description': 'Recruiting team'},
}]
_OBJ_PERM_ROWS = [{
    'SobjectType': 'Account', 'PermissionsRead': True, 'PermissionsCreate': True,
    'PermissionsEdit': True, 'PermissionsDelete': False,
    'PermissionsViewAllRecords': False, 'PermissionsModifyAllRecords': False,
}]


def test_get_user_detail_returns_full_picture():
    sf = _routed_sf(
        query_map={'FROM User': _USER_DETAIL_ROW},
        query_all_map={
            'FROM PermissionSetAssignment': _USER_PSET_ASSIGN,
            'FROM ObjectPermissions': _OBJ_PERM_ROWS,
        },
    )
    with patch('services.perm_auditor.get_sf', return_value=sf):
        detail = perm_auditor.get_user_detail('dev', '005000000000001')
    assert detail['id'] == '005000000000001'
    assert 'permission_sets' in detail
    assert 'object_permissions' in detail
    assert isinstance(detail['permission_sets'], list)
    assert isinstance(detail['object_permissions'], list)
    assert len(detail['permission_sets']) == 1
    assert detail['object_permissions'][0]['object'] == 'Account'


class _EmptySF:
    """SF stub whose queries return no records — models a lookup miss."""
    def query(self, soql):
        return {'records': []}

    def query_all(self, soql):
        return {'records': []}


def test_get_user_detail_unknown_user_returns_empty(monkeypatch):
    monkeypatch.setattr(perm_auditor, 'get_sf', lambda org: _EmptySF())
    assert perm_auditor.get_user_detail('dev', '005000000000000XXX') == {}


# ── Permission Set Detail ─────────────────────────────────────────────────────

_PSET_DETAIL_ROW = [{
    'Id': '0PS000000000001', 'Name': 'Recruiter', 'Label': 'Recruiter Access',
    'Description': 'Recruiting team', 'IsCustom': True, 'Type': 'Regular',
}]
_PSET_USERS = [{
    'Assignee': {'Id': '005000000000001', 'Name': 'Alice Admin',
                 'Username': 'alice@doane.edu'},
}]
_FIELD_PERM_ROWS = [{
    'SobjectType': 'Account', 'Field': 'Account.SIS_ID__c',
    'PermissionsRead': True, 'PermissionsEdit': False,
}]


def test_get_pset_detail_returns_full_picture():
    sf = _routed_sf(
        query_map={'FROM PermissionSet': _PSET_DETAIL_ROW},
        query_all_map={
            'FROM PermissionSetAssignment': _PSET_USERS,
            'FROM ObjectPermissions': _OBJ_PERM_ROWS,
            'FROM FieldPermissions': _FIELD_PERM_ROWS,
        },
    )
    with patch('services.perm_auditor.get_sf', return_value=sf):
        detail = perm_auditor.get_pset_detail('dev', '0PS000000000001')
    assert detail['id'] == '0PS000000000001'
    for key in ('users', 'object_permissions', 'field_permissions'):
        assert key in detail
        assert isinstance(detail[key], list)
    assert len(detail['users']) == 1
    assert len(detail['field_permissions']) == 1


def test_get_pset_detail_unknown_returns_empty(monkeypatch):
    monkeypatch.setattr(perm_auditor, 'get_sf', lambda org: _EmptySF())
    assert perm_auditor.get_pset_detail('dev', '0PS000000000000XXX') == {}


# ── Matrices ──────────────────────────────────────────────────────────────────

_OBJ_MATRIX_ROWS = [{
    'Parent': {'Id': '0PS000000000001', 'Name': 'Recruiter', 'Label': 'Recruiter Access'},
    'PermissionsRead': True, 'PermissionsCreate': True, 'PermissionsEdit': True,
    'PermissionsDelete': False, 'PermissionsViewAllRecords': False,
    'PermissionsModifyAllRecords': False,
}]
_FIELD_MATRIX_ROWS = [{
    'Parent': {'Id': '0PS000000000001', 'Name': 'Recruiter', 'Label': 'Recruiter Access'},
    'Field': 'Account.SIS_ID__c', 'PermissionsRead': True, 'PermissionsEdit': False,
}]


def test_get_object_access_matrix_shape():
    sf = _routed_sf(query_all_default=_OBJ_MATRIX_ROWS)
    with patch('services.perm_auditor.get_sf', return_value=sf):
        result = perm_auditor.get_object_access_matrix('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert isinstance(result['rows'], list)
    assert len(result['rows']) == 1
    assert result['rows'][0]['pset_label'] == 'Recruiter Access'


def test_get_field_access_matrix_shape():
    sf = _routed_sf(query_all_default=_FIELD_MATRIX_ROWS)
    with patch('services.perm_auditor.get_sf', return_value=sf):
        result = perm_auditor.get_field_access_matrix('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert isinstance(result['fields'], list)
    assert result['fields'][0]['field'] == 'SIS_ID__c'


# ── Legacy helpers (kept for backward compat) ─────────────────────────────────

def test_legacy_get_assignments_runs():
    rows = [{'Id': '0Pa000000000001',
             'PermissionSet': {'Name': 'Recruiter', 'Label': 'Recruiter Access',
                               'IsOwnedByProfile': False},
             'Assignee': {'Name': 'Alice Admin', 'Username': 'alice@doane.edu'}}]
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=rows)):
        result = perm_auditor.get_assignments('dev')
    assert isinstance(result, list)
    assert len(result) == 1


def test_legacy_get_field_access_runs():
    rows = [{'Id': '0Pf000000000001', 'SobjectType': 'Account',
             'Field': 'Account.SIS_ID__c', 'PermissionsRead': True, 'PermissionsEdit': True}]
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=rows)):
        result = perm_auditor.get_field_access('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert 'permissions' in result


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_route_perm_sets(client):
    with patch('services.perm_auditor.get_sf', return_value=_perm_sets_sf()):
        resp = client.get('/api/v1/admin/permissions/sets')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_users(client):
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=_USER_ROWS)):
        resp = client.get('/api/v1/admin/permissions/users')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_user_detail(client):
    sf = _routed_sf(
        query_map={'FROM User': _USER_DETAIL_ROW},
        query_all_map={
            'FROM PermissionSetAssignment': _USER_PSET_ASSIGN,
            'FROM ObjectPermissions': _OBJ_PERM_ROWS,
        },
    )
    with patch('services.perm_auditor.get_sf', return_value=sf):
        resp = client.get('/api/v1/admin/permissions/user/005000000000001')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_set_detail(client):
    sf = _routed_sf(
        query_map={'FROM PermissionSet': _PSET_DETAIL_ROW},
        query_all_map={
            'FROM PermissionSetAssignment': _PSET_USERS,
            'FROM ObjectPermissions': _OBJ_PERM_ROWS,
            'FROM FieldPermissions': _FIELD_PERM_ROWS,
        },
    )
    with patch('services.perm_auditor.get_sf', return_value=sf):
        resp = client.get('/api/v1/admin/permissions/set/0PS000000000001')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_object_matrix_requires_object_param(client):
    resp = client.get('/api/v1/admin/permissions/object-matrix')
    assert resp.status_code == 400


def test_route_object_matrix_with_param(client):
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=_OBJ_MATRIX_ROWS)):
        resp = client.get('/api/v1/admin/permissions/object-matrix?object=Account')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_field_matrix_requires_object_param(client):
    resp = client.get('/api/v1/admin/permissions/field-matrix')
    assert resp.status_code == 400


def test_route_field_matrix_with_param(client):
    with patch('services.perm_auditor.get_sf', return_value=_routed_sf(query_all_default=_FIELD_MATRIX_ROWS)):
        resp = client.get('/api/v1/admin/permissions/field-matrix?object=Account')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_sets_error_returns_500(client, monkeypatch):
    import services.perm_auditor as pa
    monkeypatch.setattr(pa, 'get_permission_sets',
                        lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.get('/api/v1/admin/permissions/sets')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
