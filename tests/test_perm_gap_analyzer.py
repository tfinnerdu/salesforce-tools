"""Tests for services/perm_gap_analyzer.py and its routes."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _wrap(records):
    return {'records': records, 'totalSize': len(records), 'done': True}


_PS_A = 'a0A000001'
_PS_B = 'a0A000002'

_PSET_ROWS = [
    {'Id': _PS_A, 'Name': 'Recruiter', 'Label': 'Recruiter Access',
     'Description': 'Recruiting team', 'IsCustom': True},
    {'Id': _PS_B, 'Name': 'Counselor', 'Label': 'Counselor Access',
     'Description': '', 'IsCustom': True},
]

_LABEL_ROWS = [
    {'Id': _PS_A, 'Label': 'Recruiter Access'},
    {'Id': _PS_B, 'Label': 'Counselor Access'},
]

# Account: A has Create, B does not -> one object gap.
_OBJ_PERM_ROWS = [
    {'SobjectType': 'Account', 'ParentId': _PS_A,
     'PermissionsRead': True, 'PermissionsCreate': True, 'PermissionsEdit': True,
     'PermissionsDelete': False, 'PermissionsViewAllRecords': False,
     'PermissionsModifyAllRecords': False},
    {'SobjectType': 'Account', 'ParentId': _PS_B,
     'PermissionsRead': True, 'PermissionsCreate': False, 'PermissionsEdit': True,
     'PermissionsDelete': False, 'PermissionsViewAllRecords': False,
     'PermissionsModifyAllRecords': False},
]

# Account.SIS_ID__c: A can Edit, B cannot -> one field gap.
_FIELD_PERM_ROWS = [
    {'SobjectType': 'Account', 'Field': 'Account.SIS_ID__c', 'ParentId': _PS_A,
     'PermissionsRead': True, 'PermissionsEdit': True},
    {'SobjectType': 'Account', 'Field': 'Account.SIS_ID__c', 'ParentId': _PS_B,
     'PermissionsRead': True, 'PermissionsEdit': False},
]


def _compare_sf():
    """SF double routing the queries perm_gap_analyzer.compare() issues."""
    def _query(soql):
        if 'FROM PermissionSet' in soql:
            return _wrap(_LABEL_ROWS)
        return _wrap([])

    def _query_all(soql):
        if 'FROM ObjectPermissions' in soql:
            return _wrap(_OBJ_PERM_ROWS)
        if 'FROM FieldPermissions' in soql:
            return _wrap(_FIELD_PERM_ROWS)
        return _wrap([])

    sf = MagicMock()
    sf.query.side_effect = _query
    sf.query_all.side_effect = _query_all
    return sf


def _list_sf():
    sf = MagicMock()
    sf.query.return_value = _wrap(_PSET_ROWS)
    return sf


# ---------------------------------------------------------------------------
# Unit tests: list_permission_sets
# ---------------------------------------------------------------------------

def test_list_permission_sets_returns_list():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_list_sf()):
        result = perm_gap_analyzer.list_permission_sets('dev')
    assert isinstance(result, list)
    assert len(result) == 2


def test_list_permission_sets_each_has_required_keys():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_list_sf()):
        result = perm_gap_analyzer.list_permission_sets('dev')
    assert len(result) > 0
    for ps in result:
        for key in ('id', 'name', 'label'):
            assert key in ps


# ---------------------------------------------------------------------------
# Unit tests: compare
# ---------------------------------------------------------------------------

def test_compare_returns_dict_with_top_level_keys():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        result = perm_gap_analyzer.compare('dev', _PS_A, _PS_B)
    assert isinstance(result, dict)
    for key in ('ps_a', 'ps_b', 'object_gaps', 'field_gaps', 'summary'):
        assert key in result, f"Missing key: {key}"


def test_compare_object_gaps_is_list():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        result = perm_gap_analyzer.compare('dev', _PS_A, _PS_B)
    assert isinstance(result['object_gaps'], list)
    # A grants Create on Account, B does not.
    assert len(result['object_gaps']) == 1
    assert result['object_gaps'][0]['permission'] == 'Create'


def test_compare_object_gaps_items_have_required_keys():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        result = perm_gap_analyzer.compare('dev', _PS_A, _PS_B)
    for gap in result['object_gaps']:
        for key in ('object', 'permission', 'in_a', 'in_b'):
            assert key in gap


def test_compare_field_gaps_is_list():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        result = perm_gap_analyzer.compare('dev', _PS_A, _PS_B)
    assert isinstance(result['field_gaps'], list)
    # A can Edit SIS_ID__c, B cannot.
    assert len(result['field_gaps']) == 1
    assert result['field_gaps'][0]['permission'] == 'Edit'


def test_compare_summary_has_required_keys():
    from services import perm_gap_analyzer
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        result = perm_gap_analyzer.compare('dev', _PS_A, _PS_B)
    summary = result['summary']
    for key in ('only_in_a', 'only_in_b', 'total_gaps'):
        assert key in summary
    # Both gaps are present in A but not B.
    assert summary['only_in_a'] == 2
    assert summary['total_gaps'] == 2


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_perm_gap_list_route_returns_200(client):
    with patch('services.perm_gap_analyzer.get_sf', return_value=_list_sf()):
        resp = client.get('/api/v1/impact/perm-gap/list')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert len(data['data']) == 2


def test_perm_gap_compare_valid_ids_returns_200(client):
    with patch('services.perm_gap_analyzer.get_sf', return_value=_compare_sf()):
        resp = client.post(
            '/api/v1/impact/perm-gap/compare',
            data=json.dumps({'ps_a': _PS_A, 'ps_b': _PS_B}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'object_gaps' in data['data']


def test_perm_gap_compare_missing_ps_a_returns_400(client):
    resp = client.post(
        '/api/v1/impact/perm-gap/compare',
        data=json.dumps({'ps_b': _PS_B}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_perm_gap_compare_same_ids_returns_400(client):
    resp = client.post(
        '/api/v1/impact/perm-gap/compare',
        data=json.dumps({'ps_a': _PS_A, 'ps_b': _PS_A}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'different' in data['error'].lower()


def test_perm_gap_compare_exception_returns_500(client):
    with patch(
        'services.perm_gap_analyzer.compare',
        side_effect=Exception('SF unavailable'),
    ):
        resp = client.post(
            '/api/v1/impact/perm-gap/compare',
            data=json.dumps({'ps_a': _PS_A, 'ps_b': _PS_B}),
            content_type='application/json',
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Legacy redirect
# ---------------------------------------------------------------------------

class TestImpactLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/impact/perm-gap/list', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/impact/perm-gap/list')

    def test_old_path_redirect_is_followable(self, client):
        with patch('services.perm_gap_analyzer.get_sf', return_value=_list_sf()):
            resp = client.get('/impact/perm-gap/list', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
