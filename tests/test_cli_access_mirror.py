"""Tests for services.cli_access_mirror + the /cli/access-mirror route and the
mirror/tab folding into the clone package.

The source and target orgs are MagicMock SF clients whose query_all responds by
inspecting the SOQL, so the group-by-parent read, the name matching, the field
scoping, and the profile/permission-set split are exercised without a live org.
"""
import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from services import cli_access_mirror as mirror
from services import cli_clone


# ── mock builders ─────────────────────────────────────────────────────────────

def _op(is_profile, name, read=True, create=False, edit=False, delete=False,
        view_all=False, modify_all=False):
    """An ObjectPermissions record for a profile (name via Profile.Name) or permset."""
    parent = ({'IsOwnedByProfile': True, 'Profile': {'Name': name}, 'Name': 'X00eXXX'}
              if is_profile else {'IsOwnedByProfile': False, 'Name': name})
    return {'Parent': parent, 'PermissionsRead': read, 'PermissionsCreate': create,
            'PermissionsEdit': edit, 'PermissionsDelete': delete,
            'PermissionsViewAllRecords': view_all, 'PermissionsModifyAllRecords': modify_all}


def _fp(is_profile, name, field, read=True, edit=False):
    parent = ({'IsOwnedByProfile': True, 'Profile': {'Name': name}, 'Name': 'X00eXXX'}
              if is_profile else {'IsOwnedByProfile': False, 'Name': name})
    return {'Field': field, 'Parent': parent,
            'PermissionsRead': read, 'PermissionsEdit': edit}


def _source_sf(object_rows, field_rows):
    sf = MagicMock()

    def q(soql):
        if 'FROM ObjectPermissions' in soql:
            return {'records': object_rows}
        if 'FROM FieldPermissions' in soql:
            return {'records': field_rows}
        return {'records': []}
    sf.query_all.side_effect = q
    return sf


def _target_sf(profiles, permsets, describe=None, objects=None):
    """profiles: iterable of names; permsets: {name: label}; describe: object
    describe payload (None => object not in target yet); objects: global-describe
    sObject names present in the target (for the Lookup-resolution check)."""
    sf = MagicMock()

    def q(soql):
        if soql.startswith('SELECT Name FROM Profile'):
            return {'records': [{'Name': n} for n in profiles]}
        if 'FROM PermissionSet' in soql:
            return {'records': [{'Name': n, 'Label': l} for n, l in permsets.items()]}
        return {'records': []}
    sf.query_all.side_effect = q
    sf.describe.return_value = {'sobjects': [{'name': n} for n in (objects or [])]}
    if describe is None:
        sf.restful.side_effect = RuntimeError('NOT_FOUND')
    else:
        sf.restful.return_value = describe
    return sf


# ── read_object_access_from ───────────────────────────────────────────────────

def test_read_groups_profile_and_permset():
    src = _source_sf(
        [_op(True, 'System Administrator', read=True, create=True, edit=True),
         _op(False, 'Housing_Staff', read=True)],
        [_fp(True, 'System Administrator', 'RoomAssignment__c.Room__c', read=True, edit=True),
         _fp(False, 'Housing_Staff', 'RoomAssignment__c.Room__c', read=True)])
    res = mirror.read_object_access_from(src, 'RoomAssignment__c')
    by_name = {p['name']: p for p in res['parents']}
    assert by_name['System Administrator']['type'] == 'Profile'
    assert by_name['System Administrator']['object_perms']['edit'] is True
    assert by_name['Housing_Staff']['type'] == 'PermissionSet'
    assert by_name['Housing_Staff']['object_perms']['edit'] is False
    # field perms carried per parent
    assert by_name['System Administrator']['field_perms'][0]['editable'] is True


def test_read_drops_all_false_parents():
    src = _source_sf([_op(True, 'Nobody', read=False)],
                     [_fp(True, 'Nobody', 'RoomAssignment__c.Room__c', read=False, edit=False)])
    res = mirror.read_object_access_from(src, 'RoomAssignment__c')
    assert res['parents'] == []


def test_read_profile_uses_profile_name_not_owned_permset_name():
    src = _source_sf([_op(True, 'Custom: Support')], [])
    res = mirror.read_object_access_from(src, 'X__c')
    assert res['parents'][0]['name'] == 'Custom: Support'   # not X00eXXX


# ── target_catalog / target_field_set ─────────────────────────────────────────

def test_target_catalog():
    tgt = _target_sf(['System Administrator', 'Standard User'],
                     {'Housing_Staff': 'Housing Staff'})
    cat = mirror.target_catalog(tgt)
    assert 'System Administrator' in cat['profiles']
    assert cat['permission_sets']['Housing_Staff'] == 'Housing Staff'


def test_target_field_set_missing_object_returns_none():
    tgt = _target_sf([], {}, describe=None)
    assert mirror.target_field_set(tgt, 'Ghost__c') is None


def test_target_field_set_lists_fields():
    tgt = _target_sf([], {}, describe={'fields': [{'name': 'Room__c'}, {'name': 'Name'}]})
    assert mirror.target_field_set(tgt, 'RoomAssignment__c') == {
        'RoomAssignment__c.Room__c', 'RoomAssignment__c.Name'}


# ── mirror_plan ───────────────────────────────────────────────────────────────

def _run_plan(cloned_fields=None, describe=None, **kw):
    # 'Housing_Manager' stands in for an ordinary (non-high-privilege) Profile
    # so these tests exercise name-matching/field-scoping, not the
    # high-privilege exclusion behavior (covered separately below).
    src = _source_sf(
        [_op(True, 'Housing_Manager', read=True, edit=True),
         _op(False, 'Housing_Staff', read=True),
         _op(False, 'Ghost_Set', read=True)],
        [_fp(True, 'Housing_Manager', 'RoomAssignment__c.Room__c', read=True, edit=True),
         _fp(True, 'Housing_Manager', 'RoomAssignment__c.Legacy__c', read=True),
         _fp(False, 'Housing_Staff', 'RoomAssignment__c.Room__c', read=True)])
    tgt = _target_sf(['Housing_Manager'], {'Housing_Staff': 'Housing Staff'},
                     describe=describe)

    def fake(org):
        return src if org == 'eda' else tgt
    with patch('services.cli_access_mirror.get_sf', side_effect=fake):
        return mirror.mirror_plan('eda', 'sandbox', 'RoomAssignment__c', cloned_fields, **kw)


def test_mirror_matches_by_name():
    plan = _run_plan(cloned_fields=['RoomAssignment__c.Room__c'])
    matched = {m['name'] for m in plan['matched']}
    unmatched = {u['name'] for u in plan['unmatched']}
    assert matched == {'Housing_Manager', 'Housing_Staff'}
    assert unmatched == {'Ghost_Set'}
    assert plan['counts']['matched_profiles'] == 1
    assert plan['counts']['matched_permsets'] == 1


def test_mirror_scopes_field_perms_to_allowed():
    # Room__c is cloned; Legacy__c is not -> dropped from the profile's grants.
    plan = _run_plan(cloned_fields=['RoomAssignment__c.Room__c'])
    admin = next(m for m in plan['matched'] if m['name'] == 'Housing_Manager')
    fields = {fp['field'] for fp in admin['field_perms']}
    assert fields == {'RoomAssignment__c.Room__c'}
    assert admin['dropped_fields'] == 1


def test_mirror_unions_target_existing_fields():
    # Legacy__c already exists in the target -> kept even though not being cloned.
    plan = _run_plan(cloned_fields=['RoomAssignment__c.Room__c'],
                     describe={'fields': [{'name': 'Legacy__c'}]})
    admin = next(m for m in plan['matched'] if m['name'] == 'Housing_Manager')
    fields = {fp['field'] for fp in admin['field_perms']}
    assert fields == {'RoomAssignment__c.Room__c', 'RoomAssignment__c.Legacy__c'}
    assert plan['target_object_exists'] is True


def test_mirror_permset_carries_target_label():
    plan = _run_plan(cloned_fields=['RoomAssignment__c.Room__c'])
    hs = next(m for m in plan['matched'] if m['name'] == 'Housing_Staff')
    assert hs['label'] == 'Housing Staff'


# ── locked-profile skip ───────────────────────────────────────────────────────

def test_locked_profile_is_skipped_not_matched():
    src = _source_sf(
        [_op(True, 'B2BMA Integration User', read=True),
         _op(True, 'Housing_Manager', read=True)],
        [_fp(True, 'B2BMA Integration User', 'RoomAssignment__c.Room__c', read=True),
         _fp(True, 'Housing_Manager', 'RoomAssignment__c.Room__c', read=True)])
    tgt = _target_sf(['B2BMA Integration User', 'Housing_Manager'], {}, describe=None)

    def fake(org):
        return src if org == 'eda' else tgt
    with patch('services.cli_access_mirror.get_sf', side_effect=fake):
        plan = mirror.mirror_plan('eda', 'sandbox', 'RoomAssignment__c',
                                  ['RoomAssignment__c.Room__c'])
    matched = {m['name'] for m in plan['matched']}
    locked = {x['name'] for x in plan['skipped_locked']}
    assert matched == {'Housing_Manager'}          # locked one dropped
    assert locked == {'B2BMA Integration User'}
    assert plan['counts']['skipped_locked'] == 1


def test_locked_profile_list_is_narrow():
    # Only the proven offender (B2BMA) is skipped; other integration/standard
    # profiles deploy additively, so they must NOT be dropped by name.
    assert mirror._is_locked_profile('B2BMA Integration User')
    assert not mirror._is_locked_profile('CPQ Integration User')          # deploys fine
    assert not mirror._is_locked_profile('Analytics Cloud Integration User')
    assert not mirror._is_locked_profile('Salesforce API Only System Integrations')
    assert not mirror._is_locked_profile('Conductor Integration')         # custom
    assert not mirror._is_locked_profile('System Administrator')


# ── high-privilege-profile exclusion ──────────────────────────────────────────

def test_high_privilege_profile_excluded_by_default():
    plan = _run_plan(cloned_fields=['RoomAssignment__c.Room__c'])
    assert plan['high_privilege_excluded'] == []   # Housing_Manager isn't high-privilege

    src = _source_sf(
        [_op(True, 'System Administrator', read=True, edit=True),
         _op(False, 'Housing_Staff', read=True)],
        [_fp(True, 'System Administrator', 'RoomAssignment__c.Room__c', read=True, edit=True),
         _fp(False, 'Housing_Staff', 'RoomAssignment__c.Room__c', read=True)])
    tgt = _target_sf(['System Administrator'], {'Housing_Staff': 'Housing Staff'}, describe=None)

    def fake(org):
        return src if org == 'eda' else tgt
    with patch('services.cli_access_mirror.get_sf', side_effect=fake):
        plan = mirror.mirror_plan('eda', 'sandbox', 'RoomAssignment__c',
                                  ['RoomAssignment__c.Room__c'])
    matched = {m['name'] for m in plan['matched']}
    excluded = {x['name'] for x in plan['high_privilege_excluded']}
    assert matched == {'Housing_Staff'}                       # admin NOT mirrored by default
    assert excluded == {'System Administrator'}                # reported, not silently dropped
    assert plan['counts']['high_privilege_excluded'] == 1


def test_high_privilege_profile_included_when_opted_in():
    src = _source_sf(
        [_op(True, 'System Administrator', read=True, edit=True)],
        [_fp(True, 'System Administrator', 'RoomAssignment__c.Room__c', read=True, edit=True)])
    tgt = _target_sf(['System Administrator'], {}, describe=None)

    def fake(org):
        return src if org == 'eda' else tgt
    with patch('services.cli_access_mirror.get_sf', side_effect=fake):
        plan = mirror.mirror_plan('eda', 'sandbox', 'RoomAssignment__c',
                                  ['RoomAssignment__c.Room__c'], include_high_privilege=True)
    matched = {m['name'] for m in plan['matched']}
    assert matched == {'System Administrator'}
    assert plan['high_privilege_excluded'] == []
    admin = next(m for m in plan['matched'] if m['name'] == 'System Administrator')
    assert admin['high_privilege'] is True   # flagged even though included


def test_is_high_privilege_helper():
    assert mirror._is_high_privilege('System Administrator')
    assert not mirror._is_high_privilege('Housing_Manager')


# ── audit emission ─────────────────────────────────────────────────────────────

def test_mirror_plan_emits_audit_event():
    # This reads a whole object's cross-profile/permission-set security
    # posture -- every call must be audited (see services/audit.py).
    with patch('services.cli_access_mirror.audit.emit') as emit:
        _run_plan(cloned_fields=['RoomAssignment__c.Room__c'], justification='onboarding staff')
    emit.assert_called_once()
    args, kwargs = emit.call_args
    assert args[0] == 'ACCESS_MIRROR_PLAN'
    assert args[1] == 'sf_object_permissions'
    assert args[2] == 'eda->sandbox:RoomAssignment__c'
    assert args[3] == 'success'
    assert kwargs['detail']['justification'] == 'onboarding staff'


def test_target_object_names_reads_global_describe():
    sf = MagicMock()
    sf.describe.return_value = {'sobjects': [{'name': 'Account'}, {'name': 'RoomAssignment__c'}]}
    assert mirror.target_object_names(sf) == {'Account', 'RoomAssignment__c'}


def test_target_object_names_none_on_failure():
    sf = MagicMock()
    sf.describe.side_effect = RuntimeError('boom')
    sf.restful.side_effect = RuntimeError('boom')
    assert mirror.target_object_names(sf) is None


# ── split_grants ──────────────────────────────────────────────────────────────

def test_split_grants_shapes():
    matched = [
        {'name': 'System Administrator', 'type': 'Profile',
         'object_perms': {'object': 'X__c', 'read': True}, 'field_perms': [{'field': 'X__c.A__c'}]},
        {'name': 'Housing_Staff', 'type': 'PermissionSet', 'label': 'Housing Staff',
         'object_perms': {'object': 'X__c', 'read': True}, 'field_perms': []},
    ]
    profiles, permsets = mirror.split_grants(matched)
    assert profiles[0]['api_name'] == 'System Administrator'
    assert isinstance(profiles[0]['object_perms'], list)   # wrapped for the generator
    assert permsets[0]['label'] == 'Housing Staff'


# ── /cli/access-mirror/plan route ─────────────────────────────────────────────

def test_route_access_mirror_plan(client):
    src = _source_sf([_op(True, 'Housing_Manager', read=True)],
                     [_fp(True, 'Housing_Manager', 'RoomAssignment__c.Room__c', read=True)])
    tgt = _target_sf(['Housing_Manager'], {}, describe=None)

    def fake(org):
        return src if org == 'sandbox' else tgt
    with patch('services.cli_access_mirror.get_sf', side_effect=fake):
        resp = client.post('/api/v1/cli/access-mirror/plan', data=json.dumps({
            'object': 'RoomAssignment__c', 'source_org': 'sandbox', 'target_org': 'dev',
            'justification': 'onboarding Housing Staff for testing'}),
            content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['counts']['matched'] == 1


def test_route_access_mirror_requires_object(client):
    resp = client.post('/api/v1/cli/access-mirror/plan', data=json.dumps({}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_route_access_mirror_rejects_unknown_org(client):
    resp = client.post('/api/v1/cli/access-mirror/plan', data=json.dumps(
        {'object': 'X__c', 'source_org': 'nope'}), content_type='application/json')
    assert resp.status_code == 400


def test_route_access_mirror_requires_justification(client):
    resp = client.post('/api/v1/cli/access-mirror/plan', data=json.dumps({
        'object': 'RoomAssignment__c', 'source_org': 'dev', 'target_org': 'dev'}),
        content_type='application/json')
    assert resp.status_code == 400
    assert 'justification' in resp.get_json()['error'].lower()


def test_route_access_mirror_rejects_short_justification(client):
    resp = client.post('/api/v1/cli/access-mirror/plan', data=json.dumps({
        'object': 'RoomAssignment__c', 'source_org': 'dev', 'target_org': 'dev',
        'justification': 'why'}), content_type='application/json')
    assert resp.status_code == 400


# ── clone package: include_tab + mirror_access folding ────────────────────────

_CLONE_DESCRIBE = {
    'label': 'Accommodation', 'labelPlural': 'Accommodations', 'custom': True,
    'fields': [
        {'name': 'Name', 'label': 'Name', 'type': 'string', 'nameField': True},
        {'name': 'Notes__c', 'label': 'Notes', 'type': 'string', 'length': 255},
    ],
}


def _clone_sf():
    sf = MagicMock()
    sf.restful.return_value = _CLONE_DESCRIBE
    return sf


def test_clone_package_with_tab(client):
    with patch('services.cli_clone.get_sf', return_value=_clone_sf()):
        resp = client.post('/api/v1/cli/clone-object/package', data=json.dumps({
            'object': 'Accommodation__c', 'include_permset': True, 'include_tab': True}),
            content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
        assert 'force-app/main/default/tabs/Accommodation__c.tab-meta.xml' in names
        ps = next(n for n in names if 'permissionsets/' in n)
        ps_xml = zf.read(ps).decode()
        pkg = zf.read('manifest/package.xml').decode()
    assert '<tabSettings><tab>Accommodation__c</tab>' in ps_xml   # visibility granted
    assert '<name>CustomTab</name>' in pkg


def test_clone_package_with_mirror(client):
    src = _clone_sf()
    mirror_src = _source_sf(
        [_op(True, 'Housing_Manager', read=True, edit=True),
         _op(False, 'Housing_Staff', read=True)],
        [_fp(True, 'Housing_Manager', 'Accommodation__c.Notes__c', read=True, edit=True)])
    tgt = _target_sf(['Housing_Manager'], {'Housing_Staff': 'Housing Staff'}, describe=None)

    def fake_mirror_sf(org):
        return mirror_src if org == 'sandbox' else tgt
    with patch('services.cli_clone.get_sf', return_value=src), \
            patch('services.cli_access_mirror.get_sf', side_effect=fake_mirror_sf):
        resp = client.post('/api/v1/cli/clone-object/package', data=json.dumps({
            'object': 'Accommodation__c', 'source_org': 'sandbox', 'target_org': 'dev',
            'include_permset': True, 'mirror_access': True,
            'justification': 'onboarding Housing Staff for testing'}),
            content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
        pkg = zf.read('manifest/package.xml').decode()
        prof = zf.read('force-app/main/default/profiles/Housing_Manager.profile-meta.xml').decode()
    # matched profile + matched permset both rode in
    assert 'force-app/main/default/profiles/Housing_Manager.profile-meta.xml' in names
    assert 'force-app/main/default/permissionsets/Housing_Staff.permissionset-meta.xml' in names
    assert '<name>Profile</name>' in pkg
    assert '<field>Accommodation__c.Notes__c</field>' in prof


def test_clone_package_requires_justification_when_mirroring(client):
    src = _clone_sf()
    with patch('services.cli_clone.get_sf', return_value=src):
        resp = client.post('/api/v1/cli/clone-object/package', data=json.dumps({
            'object': 'Accommodation__c', 'source_org': 'dev', 'target_org': 'dev',
            'mirror_access': True}), content_type='application/json')
    assert resp.status_code == 400
    assert 'justification' in resp.get_json()['error'].lower()


def test_clone_plan_includes_mirror_preview(client):
    src = _clone_sf()
    mirror_src = _source_sf([_op(True, 'Housing_Manager', read=True)],
                            [_fp(True, 'Housing_Manager', 'Accommodation__c.Notes__c', read=True)])
    tgt = _target_sf(['Housing_Manager'], {}, describe=None)

    def fake_mirror_sf(org):
        return mirror_src if org == 'sandbox' else tgt
    with patch('services.cli_clone.get_sf', return_value=src), \
            patch('services.cli_access_mirror.get_sf', side_effect=fake_mirror_sf):
        resp = client.post('/api/v1/cli/clone-object/plan', data=json.dumps({
            'object': 'Accommodation__c', 'source_org': 'sandbox', 'target_org': 'dev',
            'mirror_access': True, 'justification': 'onboarding Housing Staff for testing'}),
            content_type='application/json')
    data = resp.get_json()['data']
    assert data['mirror']['counts']['matched'] == 1


# ── main builder: generate_tabs for new objects ───────────────────────────────

def test_generate_tabs_for_new_object(client):
    resp = client.post('/api/v1/cli/generate', data=json.dumps({
        'alias': 'UAT',
        'fields': [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}],
        'new_objects': [{'object': 'Foo__c', 'label': 'Foo'}],
        'generate_tabs': True,
    }), content_type='application/json')
    data = resp.get_json()['data']
    assert data['has_tabs'] is True
    assert 'CustomTab:Foo__c' in data['deploy_full']


def test_package_tab_and_permset_tab_visibility(client):
    resp = client.post('/api/v1/cli/package', data=json.dumps({
        'project': 'p', 'alias': 'UAT',
        'fields': [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar',
                    'type': 'Text', 'readable': True, 'editable': True}],
        'new_objects': [{'object': 'Foo__c', 'label': 'Foo'}],
        'generate_tabs': True,
        'human_permset': {'api_name': 'Foo_Vis', 'label': 'Foo Vis', 'editable': True},
    }), content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
        vis = zf.read('force-app/main/default/permissionsets/Foo_Vis.permissionset-meta.xml').decode()
    assert 'force-app/main/default/tabs/Foo__c.tab-meta.xml' in names
    assert '<tabSettings><tab>Foo__c</tab><visibility>Visible</visibility></tabSettings>' in vis
