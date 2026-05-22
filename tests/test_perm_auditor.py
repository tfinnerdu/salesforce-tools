"""Tests for services.perm_auditor — permission sets, users, object/field matrices."""
import pytest

from services import perm_auditor


# ── Permission Sets ───────────────────────────────────────────────────────────

def test_get_permission_sets_returns_list():
    psets = perm_auditor.get_permission_sets('dev')
    assert isinstance(psets, list)
    assert len(psets) >= 1
    for key in ('id', 'name', 'label', 'description', 'is_custom', 'type', 'user_count'):
        assert key in psets[0]


def test_permission_set_user_count_is_int():
    psets = perm_auditor.get_permission_sets('dev')
    assert all(isinstance(p['user_count'], int) for p in psets)


# ── Users ─────────────────────────────────────────────────────────────────────

def test_get_users_returns_list():
    users = perm_auditor.get_users('dev')
    assert isinstance(users, list)
    assert len(users) >= 1
    for key in ('id', 'name', 'username', 'email', 'profile_name'):
        assert key in users[0]


def test_get_users_search_filter_runs():
    """Search term is accepted and a list is returned (mock ignores the filter)."""
    users = perm_auditor.get_users('dev', search='User')
    assert isinstance(users, list)


# ── User Detail ───────────────────────────────────────────────────────────────

def test_get_user_detail_returns_full_picture():
    users = perm_auditor.get_users('dev')
    detail = perm_auditor.get_user_detail('dev', users[0]['id'])
    assert detail['id'] == users[0]['id']
    assert 'permission_sets' in detail
    assert 'object_permissions' in detail
    assert isinstance(detail['permission_sets'], list)
    assert isinstance(detail['object_permissions'], list)


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

def test_get_pset_detail_returns_full_picture():
    psets = perm_auditor.get_permission_sets('dev')
    detail = perm_auditor.get_pset_detail('dev', psets[0]['id'])
    assert detail['id'] == psets[0]['id']
    for key in ('users', 'object_permissions', 'field_permissions'):
        assert key in detail
        assert isinstance(detail[key], list)


def test_get_pset_detail_unknown_returns_empty(monkeypatch):
    monkeypatch.setattr(perm_auditor, 'get_sf', lambda org: _EmptySF())
    assert perm_auditor.get_pset_detail('dev', '0PS000000000000XXX') == {}


# ── Matrices ──────────────────────────────────────────────────────────────────

def test_get_object_access_matrix_shape():
    result = perm_auditor.get_object_access_matrix('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert isinstance(result['rows'], list)


def test_get_field_access_matrix_shape():
    result = perm_auditor.get_field_access_matrix('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert isinstance(result['fields'], list)


# ── Legacy helpers (kept for backward compat) ─────────────────────────────────

def test_legacy_get_assignments_runs():
    assert isinstance(perm_auditor.get_assignments('dev'), list)


def test_legacy_get_field_access_runs():
    result = perm_auditor.get_field_access('dev', 'Account')
    assert result['object_name'] == 'Account'
    assert 'permissions' in result


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_route_perm_sets(client):
    resp = client.get('/admin/permissions/sets')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_users(client):
    resp = client.get('/admin/permissions/users')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_user_detail(client):
    resp = client.get('/admin/permissions/user/005000000000000001')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_set_detail(client):
    resp = client.get('/admin/permissions/set/0PS000000000000001')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_object_matrix_requires_object_param(client):
    resp = client.get('/admin/permissions/object-matrix')
    assert resp.status_code == 400


def test_route_object_matrix_with_param(client):
    resp = client.get('/admin/permissions/object-matrix?object=Account')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_field_matrix_requires_object_param(client):
    resp = client.get('/admin/permissions/field-matrix')
    assert resp.status_code == 400


def test_route_field_matrix_with_param(client):
    resp = client.get('/admin/permissions/field-matrix?object=Account')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_perm_sets_error_returns_500(client, monkeypatch):
    import services.perm_auditor as pa
    monkeypatch.setattr(pa, 'get_permission_sets',
                        lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.get('/admin/permissions/sets')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
