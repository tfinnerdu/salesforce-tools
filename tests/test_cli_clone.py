"""Tests for services.cli_clone + the /cli/clone-object routes and the
cli_script object-shell additions.

A source object's describe is a MagicMock return, so the describe → field-spec
mapping, the skip/report rules, the CustomObject shell, and the packaged zip are
all exercised without a live org.
"""
import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from services import cli_clone, cli_script

# A describe payload spanning the reproducible types and every skip reason.
_DESCRIBE = {
    'label': 'Accommodation', 'labelPlural': 'Accommodations', 'custom': True,
    'fields': [
        {'name': 'Name', 'label': 'Name', 'type': 'string', 'nameField': True},   # standard
        {'name': 'Notes__c', 'label': 'Notes', 'type': 'string', 'length': 255, 'nillable': True},
        {'name': 'Status__c', 'label': 'Status', 'type': 'picklist', 'restrictedPicklist': True,
         'picklistValues': [
             {'value': 'New', 'label': 'New', 'active': True, 'defaultValue': True},
             {'value': 'Old', 'label': 'Old', 'active': False, 'defaultValue': False}]},
        {'name': 'Score__c', 'label': 'Score', 'type': 'double', 'precision': 5, 'scale': 2},
        {'name': 'SIS_ID__c', 'label': 'SIS', 'type': 'string', 'length': 18,
         'externalId': True, 'unique': True},
        {'name': 'Bio__c', 'label': 'Bio', 'type': 'textarea', 'length': 5000},        # LongTextArea
        {'name': 'Active__c', 'label': 'Active', 'type': 'boolean', 'defaultValue': True},  # Checkbox
        {'name': 'Contact__c', 'label': 'Contact', 'type': 'reference',                 # plain Lookup
         'referenceTo': ['Contact'], 'relationshipName': 'Accommodations', 'nillable': True},
        # ── skip cases ──
        {'name': 'Parent__c', 'label': 'Parent', 'type': 'reference',                   # master-detail
         'referenceTo': ['Program__c'], 'relationshipOrder': 0},
        {'name': 'Poly__c', 'label': 'Poly', 'type': 'reference',                       # polymorphic
         'referenceTo': ['Account', 'Contact']},
        {'name': 'Total__c', 'label': 'Total', 'type': 'double', 'calculated': True},   # formula/rollup
        {'name': 'Auto__c', 'label': 'Auto', 'type': 'string', 'autoNumber': True},     # auto-number
        {'name': 'Cost__c', 'label': 'Cost', 'type': 'currency'},                       # unsupported type
        {'name': 'Rich__c', 'label': 'Rich', 'type': 'textarea', 'htmlFormatted': True},  # rich text
    ],
}


def _sf(describe=_DESCRIBE):
    sf = MagicMock()
    sf.restful.return_value = describe
    return sf


def _plan(**kw):
    with patch('services.cli_clone.get_sf', return_value=_sf(kw.pop('describe', _DESCRIBE))):
        return cli_clone.plan_from_object('dev', kw.pop('object', 'Accommodation__c'), **kw)


# ── plan_from_object: counts + skip rules ─────────────────────────────────────

def test_plan_counts():
    p = _plan()
    assert p['counts']['custom_fields'] == 7      # Notes, Status, Score, SIS_ID, Bio, Active, Contact
    assert p['counts']['skipped'] == 6            # Parent(MD), Poly, Total, Auto, Cost, Rich
    assert p['counts']['standard_fields'] == 1    # Name


def test_plan_skips_report_reasons():
    reasons = {s['api_name']: s['reason'] for s in _plan()['skipped']}
    assert 'master-detail' in reasons['Parent__c']
    assert 'polymorphic' in reasons['Poly__c']
    assert 'formula' in reasons['Total__c'] or 'roll-up' in reasons['Total__c']
    assert 'auto-number' in reasons['Auto__c']
    assert 'unsupported' in reasons['Cost__c']
    assert 'rich text' in reasons['Rich__c']


def test_plan_clones_plain_lookup():
    lk = next(f for f in _plan()['fields'] if f['api_name'] == 'Contact__c')
    assert lk['type'] == 'Lookup'
    assert lk['referenceTo'] == 'Contact'
    assert lk['relationshipName'] == 'Accommodations'
    assert lk['deleteConstraint'] == 'SetNull'


def test_plan_field_specs():
    by_name = {f['api_name']: f for f in _plan()['fields']}
    assert by_name['Notes__c']['type'] == 'Text'
    assert by_name['Score__c'] == {**by_name['Score__c'], 'type': 'Number', 'precision': 5, 'scale': 2}
    assert by_name['SIS_ID__c']['externalId'] is True and by_name['SIS_ID__c']['unique'] is True
    assert by_name['Bio__c']['type'] == 'LongTextArea' and by_name['Bio__c']['length'] == 5000
    assert by_name['Active__c']['type'] == 'Checkbox' and by_name['Active__c']['defaultValue'] is True


def test_plan_picklist_values_preserved():
    status = next(f for f in _plan()['fields'] if f['api_name'] == 'Status__c')
    pv = status['picklist']
    assert pv['restricted'] is True
    vals = {v['value']: v for v in pv['values']}
    assert vals['New']['default'] is True
    assert vals['Old']['active'] is False


def test_plan_specs_are_valid_for_generator():
    # Every produced spec must render without the field generator raising.
    for f in _plan()['fields']:
        assert cli_script.field_meta_xml(f).startswith(cli_script.XML_HEADER)


def test_plan_shell_off_by_default():
    assert _plan()['shell'] is None


def test_plan_shell_when_requested():
    shell = _plan(include_shell=True)['shell']
    assert shell['label'] == 'Accommodation'
    assert shell['plural_label'] == 'Accommodations'
    assert shell['name_label'] == 'Name'
    assert shell['sharing_model'] == 'ReadWrite'


def test_plan_no_shell_for_standard_object():
    desc = {'label': 'Account', 'custom': False, 'fields': [
        {'name': 'Foo__c', 'label': 'Foo', 'type': 'string', 'length': 10}]}
    assert _plan(object='Account', describe=desc, include_shell=True)['shell'] is None


def test_plan_requires_object():
    with pytest.raises(ValueError):
        _plan(object='  ')


# ── cli_script: Lookup field XML ──────────────────────────────────────────────

def test_lookup_field_meta_xml():
    xml = cli_script.field_meta_xml({
        'object': 'Accommodation__c', 'api_name': 'Contact__c', 'label': 'Contact',
        'type': 'Lookup', 'referenceTo': 'Contact', 'relationshipName': 'Accommodations',
        'deleteConstraint': 'Restrict'})
    assert '<type>Lookup</type>' in xml
    assert '<referenceTo>Contact</referenceTo>' in xml
    assert '<relationshipName>Accommodations</relationshipName>' in xml
    assert '<deleteConstraint>Restrict</deleteConstraint>' in xml


def test_lookup_relationship_name_defaults_from_api():
    xml = cli_script.field_meta_xml({
        'object': 'Accommodation__c', 'api_name': 'Contact__c', 'label': 'Contact',
        'type': 'Lookup', 'referenceTo': 'Contact'})
    assert '<relationshipName>Contact</relationshipName>' in xml   # __c stripped
    assert '<deleteConstraint>SetNull</deleteConstraint>' in xml   # default


def test_lookup_requires_reference_to():
    with pytest.raises(ValueError):
        cli_script.field_meta_xml({'api_name': 'X__c', 'label': 'X', 'type': 'Lookup'})


# ── cli_script: object shell XML + zip ────────────────────────────────────────

def test_object_meta_xml():
    xml = cli_script.object_meta_xml({
        'object': 'Accommodation__c', 'label': 'Accommodation',
        'plural_label': 'Accommodations', 'name_label': 'Name', 'sharing_model': 'ReadWrite'})
    assert '<CustomObject' in xml
    assert '<label>Accommodation</label>' in xml
    assert '<pluralLabel>Accommodations</pluralLabel>' in xml
    assert '<sharingModel>ReadWrite</sharingModel>' in xml
    assert '<type>Text</type>' in xml


def test_build_package_zip_with_object_shell():
    fields = [{'object': 'Accommodation__c', 'api_name': 'Notes__c', 'label': 'Notes', 'type': 'Text'}]
    shell = {'object': 'Accommodation__c', 'label': 'Accommodation',
             'plural_label': 'Accommodations', 'name_label': 'Name', 'sharing_model': 'ReadWrite'}
    zip_bytes, name = cli_script.build_package_zip('proj', fields, None, 'UAT', object_shells=[shell])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert 'force-app/main/default/objects/Accommodation__c/Accommodation__c.object-meta.xml' in names
        assert 'force-app/main/default/objects/Accommodation__c/fields/Notes__c.field-meta.xml' in names
        pkg = zf.read('manifest/package.xml').decode()
    assert '<name>CustomObject</name>' in pkg
    assert '<members>Accommodation__c</members>' in pkg


def test_build_package_zip_with_layout():
    layouts = [{'full_name': 'RoomAssignment__c-Room Assignment Layout',
                'xml': '<?xml version="1.0"?>\n<Layout xmlns="x"><foo/></Layout>\n'}]
    zip_bytes, _ = cli_script.build_package_zip('p', [], None, 'UAT', layouts=layouts)
    path = 'force-app/main/default/layouts/RoomAssignment__c-Room Assignment Layout.layout-meta.xml'
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert path in zf.namelist()
        assert '<Layout' in zf.read(path).decode()        # verbatim copy
        pkg = zf.read('manifest/package.xml').decode()
    assert '<name>Layout</name>' in pkg
    assert '<members>RoomAssignment__c-Room Assignment Layout</members>' in pkg


def test_deploy_snippet_includes_layout_member():
    s = cli_script.deploy_snippet([], '', 'UAT', layout_names=['Foo__c-Bar Layout'])
    assert 'Layout:Foo__c-Bar Layout' in s


def test_build_package_zip_object_only():
    # Shell with no fields still packages (create-the-object case).
    shell = {'object': 'Foo__c', 'label': 'Foo', 'plural_label': 'Foos', 'name_label': 'Name'}
    zip_bytes, _ = cli_script.build_package_zip('p', [], None, '', object_shells=[shell])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert 'force-app/main/default/objects/Foo__c/Foo__c.object-meta.xml' in zf.namelist()


# ── cli_script: layout-list snippet + deploy with object shells ───────────────

def test_layout_list_snippet():
    s = cli_script.layout_list_snippet('UAT')
    assert 'list metadata' in s and 'Layout' in s and 'UAT' in s


def test_deploy_snippet_puts_object_before_its_fields():
    s = cli_script.deploy_snippet(
        [{'object': 'Foo__c', 'api_name': 'Bar__c'}], '', 'UAT', object_names=['Foo__c'])
    assert s.index('CustomObject:Foo__c') < s.index('CustomField:Foo__c.Bar__c')


def test_members_prepends_custom_objects():
    members = cli_script._members(
        [{'object': 'Foo__c', 'api_name': 'Bar__c'}], '', None, ['Foo__c'])
    assert members[0] == 'CustomObject:Foo__c'


# ── Routes ────────────────────────────────────────────────────────────────────

def test_route_plan_honors_source_org(client, monkeypatch):
    captured = {}

    def fake_plan(org, obj, include_shell=False):
        captured['org'] = org
        return {'object': obj, 'label': obj, 'is_custom': True, 'fields': [],
                'skipped': [], 'shell': None,
                'counts': {'custom_fields': 0, 'skipped': 0, 'standard_fields': 0, 'total_fields': 0}}

    monkeypatch.setattr(cli_clone, 'plan_from_object', fake_plan)
    resp = client.post('/cli/clone-object/plan',
                       data=json.dumps({'object': 'Foo__c', 'source_org': 'sandbox'}),
                       content_type='application/json')
    assert resp.status_code == 200
    assert captured['org'] == 'sandbox'


def test_route_plan_rejects_unknown_source_org(client):
    resp = client.post('/cli/clone-object/plan',
                       data=json.dumps({'object': 'Foo__c', 'source_org': 'nope'}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_generate_includes_layout_list_and_new_object_deploy(client):
    resp = client.post('/cli/generate', data=json.dumps({
        'alias': 'UAT',
        'fields': [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}],
        'new_objects': [{'object': 'Foo__c', 'label': 'Foo'}],
    }), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'list metadata' in data['layout_list']
    assert data['has_new_objects'] is True
    assert 'CustomObject:Foo__c' in data['deploy_full']


def test_package_includes_new_object_shell(client):
    resp = client.post('/cli/package', data=json.dumps({
        'project': 'proj', 'alias': 'UAT',
        'fields': [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}],
        'new_objects': [{'object': 'Foo__c', 'label': 'Foo', 'plural_label': 'Foos'}],
    }), content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
    assert any(n.endswith('Foo__c.object-meta.xml') for n in names)


def test_new_object_bad_api_name_rejected(client):
    resp = client.post('/cli/package', data=json.dumps({
        'project': 'p', 'alias': 'UAT', 'fields': [],
        'new_objects': [{'object': 'NoSuffix', 'label': 'X'}],
    }), content_type='application/json')
    assert resp.status_code == 400


def test_package_includes_pasted_layout(client):
    resp = client.post('/cli/package', data=json.dumps({
        'project': 'p', 'alias': 'UAT', 'fields': [],
        'layouts': [{'full_name': 'RoomAssignment__c-Room Assignment Layout',
                     'xml': '<?xml version="1.0"?><Layout xmlns="x">stuff</Layout>'}],
    }), content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        assert any(n.endswith('Room Assignment Layout.layout-meta.xml') for n in zf.namelist())


def test_generate_layout_rides_in_deploy(client):
    resp = client.post('/cli/generate', data=json.dumps({
        'alias': 'UAT',
        'layouts': [{'full_name': 'Foo__c-Bar', 'xml': '<Layout>x</Layout>'}],
    }), content_type='application/json')
    data = resp.get_json()['data']
    assert 'Layout:Foo__c-Bar' in data['deploy_full']
    assert data['has_layouts'] is True


def test_layout_not_layout_xml_rejected(client):
    resp = client.post('/cli/package', data=json.dumps({
        'project': 'p', 'alias': 'UAT', 'fields': [],
        'layouts': [{'full_name': 'Foo__c-Bar', 'xml': '<NotALayout/>'}],
    }), content_type='application/json')
    assert resp.status_code == 400


def test_generate_retrieve_from_source_deploy_to_target(client):
    # Retrieve layout/record type FROM 'eda', deploy TO the target alias 'UAT'.
    resp = client.post('/cli/generate', data=json.dumps({
        'alias': 'UAT',
        'layout_name': 'Case-Case Layout', 'layout_retrieve_alias': 'eda',
        'recordtype_name': 'Case.Advisee', 'rt_retrieve_alias': 'eda',
    }), content_type='application/json')
    data = resp.get_json()['data']
    assert '--target-org eda' in data['layout_list']   # list uses --target-org
    assert '-o eda' in data['layout_retrieve']
    assert '-o eda' in data['recordtype_retrieve']
    assert '-o UAT' in data['layout_deploy']        # deploy targets the top alias
    assert '-o UAT' in data['recordtype_deploy']


def test_generate_retrieve_alias_defaults_to_target(client):
    resp = client.post('/cli/generate', data=json.dumps({
        'alias': 'UAT', 'layout_name': 'Case-Case Layout',
    }), content_type='application/json')
    data = resp.get_json()['data']
    assert '-o UAT' in data['layout_retrieve']       # blank retrieve alias → target


def test_generate_visibility_assign_uses_integration_username(client, monkeypatch):
    import routes.cli as cli_routes
    monkeypatch.setattr(cli_routes, 'get_org_config', lambda org: {'username': 'integ@doane.edu'})
    resp = client.post('/cli/generate', data=json.dumps({
        'alias': 'UAT',
        'fields': [{'object': 'Case', 'api_name': 'Foo__c', 'label': 'Foo', 'type': 'Text'}],
        'permset': {'api_name': 'Case_Integration', 'label': 'Case Integration',
                    'field_perms': [{'field': 'Case.Foo__c', 'readable': True, 'editable': True}]},
        'human_permset': {'api_name': 'Case_Vis', 'label': 'Case Vis', 'editable': True},
    }), content_type='application/json')
    data = resp.get_json()['data']
    # Both the integration and the visibility permset assign to the real username.
    assert data['assign'].count('integ@doane.edu') >= 2
    assert '<staff-username>' not in data['assign']

def test_route_plan(client):
    with patch('services.cli_clone.get_sf', return_value=_sf()):
        resp = client.post('/cli/clone-object/plan',
                           data=json.dumps({'object': 'Accommodation__c'}),
                           content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['counts']['custom_fields'] == 7
    assert data['shell'] is None


def test_route_plan_requires_object(client):
    resp = client.post('/cli/clone-object/plan', data=json.dumps({}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_route_package_returns_zip(client):
    with patch('services.cli_clone.get_sf', return_value=_sf()):
        resp = client.post('/cli/clone-object/package',
                           data=json.dumps({'object': 'Accommodation__c', 'include_permset': True}),
                           content_type='application/json')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
    assert any(n.endswith('Notes__c.field-meta.xml') for n in names)
    assert any('permissionsets/' in n for n in names)   # include_permset


def test_route_package_with_shell(client):
    with patch('services.cli_clone.get_sf', return_value=_sf()):
        resp = client.post('/cli/clone-object/package',
                           data=json.dumps({'object': 'Accommodation__c', 'include_shell': True}),
                           content_type='application/json')
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        assert any(n.endswith('Accommodation__c.object-meta.xml') for n in zf.namelist())
