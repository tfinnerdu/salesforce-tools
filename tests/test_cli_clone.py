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


def test_build_package_zip_object_only():
    # Shell with no fields still packages (create-the-object case).
    shell = {'object': 'Foo__c', 'label': 'Foo', 'plural_label': 'Foos', 'name_label': 'Name'}
    zip_bytes, _ = cli_script.build_package_zip('p', [], None, '', object_shells=[shell])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert 'force-app/main/default/objects/Foo__c/Foo__c.object-meta.xml' in zf.namelist()


# ── Routes ────────────────────────────────────────────────────────────────────

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
