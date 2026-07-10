"""Route-level tests for the cli blueprint.

The service layer is unit-tested in test_cli_metadata / test_cli_script; these
verify HTTP wiring: page render, the {success, data} envelope, describe-driven
metadata endpoints (with cli_metadata patched so no live SF is needed), the
generate payload, the zip download, and the standards error envelope
({success:false, error, code, request_id}).
"""
import io
import zipfile

import routes.cli as route


class TestPage:
    def test_index_renders(self, client):
        resp = client.get('/cli')
        assert resp.status_code == 200
        assert b'CLI' in resp.data


class TestMetadata:
    def test_objects_envelope(self, client, monkeypatch):
        monkeypatch.setattr(route.cli_metadata, 'list_objects',
                            lambda org: [{'name': 'Account', 'label': 'Account',
                                          'custom': False, 'queryable': True}])
        resp = client.get('/cli/objects')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data'][0]['name'] == 'Account'

    def test_fields_envelope(self, client, monkeypatch):
        monkeypatch.setattr(route.cli_metadata, 'describe_fields',
                            lambda org, obj: {'object': obj, 'fields': []})
        resp = client.get('/cli/objects/Account/fields')
        assert resp.status_code == 200
        assert resp.get_json()['data']['object'] == 'Account'

    def test_objects_error_envelope(self, client, monkeypatch):
        def _boom(org):
            raise RuntimeError('no creds for org')
        monkeypatch.setattr(route.cli_metadata, 'list_objects', _boom)
        resp = client.get('/cli/objects')
        assert resp.status_code == 502
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == 'SF_DESCRIBE_FAILED'
        assert 'request_id' in body and body['request_id'] != 'unknown'


class TestFls:
    def test_fls_read_envelope(self, client, monkeypatch):
        monkeypatch.setattr(route.cli_fls, 'read_field_fls',
                            lambda org, obj, field: {'object': obj, 'field': f'{obj}.{field}',
                                                     'parents': [], 'summary': {'suggested_editable': False}})
        resp = client.get('/cli/fls?org=dev&object=Case&field=X__c')
        assert resp.status_code == 200
        assert resp.get_json()['data']['field'] == 'Case.X__c'

    def test_fls_requires_object_and_field(self, client):
        resp = client.get('/cli/fls?org=dev&object=Case')
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'

    def test_fls_rejects_unknown_org(self, client):
        resp = client.get('/cli/fls?org=nope&object=Case&field=X__c')
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'


class TestGenerate:
    def _plan(self, **over):
        plan = {
            'alias': 'DoaneUAT',
            'instance_url': 'https://x--full.sandbox.my.salesforce.com',
            'project': 'doane-sf',
            'fields': [{'object': 'Account', 'api_name': 'SIS_ID__c', 'label': 'SIS ID',
                        'type': 'Text', 'length': 36, 'externalId': True, 'unique': True,
                        'mode': 'create', 'readable': True, 'editable': True}],
            'permset': {'api_name': 'SF_Tools_Importer', 'label': 'SF Tools Importer',
                        'field_perms': [{'field': 'Account.SIS_ID__c', 'readable': True, 'editable': True}]},
        }
        plan.update(over)
        return plan

    def test_generate_returns_all_snippets(self, client):
        resp = client.post('/cli/generate', json=self._plan())
        assert resp.status_code == 200
        d = resp.get_json()['data']
        for key in ('install', 'login', 'project', 'retrieve', 'deploy_dry_run',
                    'deploy_full', 'assign', 'members'):
            assert key in d
        assert 'CustomField:Account.SIS_ID__c' in d['members']
        assert d['has_flips'] is False
        assert '--instance-url https://x--full.sandbox.my.salesforce.com' in d['login']

    def test_generate_flip_toggles_backup_verify(self, client):
        plan = self._plan()
        plan['fields'][0]['mode'] = 'flip'
        d = client.post('/cli/generate', json=plan).get_json()['data']
        assert d['has_flips'] is True
        assert '--target-metadata-dir ./_backup' in d['backup']
        assert 'ForEach-Object' in d['verify']

    def test_generate_rejects_bad_field(self, client):
        plan = self._plan()
        plan['fields'][0]['api_name'] = 'SIS_ID'  # missing __c
        resp = client.post('/cli/generate', json=plan)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False and body['code'] == 'INVALID_INPUT'
        assert '__c' in body['error']

    def test_generate_with_human_permset(self, client):
        plan = self._plan()
        plan['human_permset'] = {'api_name': 'Case_Assistance_Fields',
                                 'label': 'Case Assistance Fields', 'editable': True}
        d = client.post('/cli/generate', json=plan).get_json()['data']
        assert d['has_human_permset'] is True
        assert 'PermissionSet:Case_Assistance_Fields' in d['members']
        assert 'PermissionSet:Case_Assistance_Fields' in d['deploy_full']
        # two assign lines: integration + human
        assert d['assign'].count('sf org assign permset') == 2
        assert 'Case_Assistance_Fields' in d['assign']

    def test_generate_readonly_companion_permset(self, client):
        plan = self._plan()
        plan['human_permset'] = {'api_name': 'Case_Assistance_Fields', 'editable': True,
                                 'readonly_companion': True}
        d = client.post('/cli/generate', json=plan).get_json()['data']
        assert 'PermissionSet:Case_Assistance_Fields' in d['members']
        assert 'PermissionSet:Case_Assistance_Fields_ReadOnly' in d['members']
        # integration + edit + read-only = 3 assign lines
        assert d['assign'].count('sf org assign permset') == 3

    def test_generate_includes_source_dir_deploy(self, client):
        d = client.post('/cli/generate', json=self._plan()).get_json()['data']
        assert d['deploy_dir'] == 'sf project deploy start --source-dir force-app -o DoaneUAT'

    def test_generate_permset_for_existing_fields_only(self, client):
        # No built fields, no integration permset — just clothe existing fields.
        plan = {'alias': 'DoaneUAT', 'fields': [], 'permset': {},
                'human_permset': {'api_name': 'Case_Assistance_Fields', 'editable': False},
                'existing_fields': ['Case.Group_Information__c', 'Case.Occurrence_Date__c']}
        d = client.post('/cli/generate', json=plan).get_json()['data']
        assert d['has_human_permset'] is True
        # deploy is permission-set only (no CustomField members)
        assert 'CustomField:' not in d['deploy_full']
        assert 'PermissionSet:Case_Assistance_Fields' in d['deploy_full']

    def test_generate_rejects_malformed_existing_field(self, client):
        plan = self._plan()
        plan['human_permset'] = {'api_name': 'PS'}
        plan['existing_fields'] = ['NotQualified']  # no Object.Field dot
        resp = client.post('/cli/generate', json=plan)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'


class TestRecordType:
    _RT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<RecordType xmlns="http://soap.sforce.com/2006/04/metadata">\n'
           '    <fullName>Advisee_Case</fullName>\n'
           '    <active>true</active>\n'
           '    <label>Advisee Case</label>\n'
           '    <picklistValues>\n'
           '        <picklist>Priority</picklist>\n'
           '        <values><fullName>High</fullName><default>false</default></values>\n'
           '    </picklistValues>\n'
           '</RecordType>\n')

    def test_recordtype_picklists(self, client):
        resp = client.post('/cli/recordtype/picklists', json={'rt_xml': self._RT})
        assert resp.status_code == 200
        assert resp.get_json()['data']['picklists'] == ['Priority']

    def test_recordtype_new_block(self, client):
        resp = client.post('/cli/recordtype', json={
            'rt_xml': self._RT, 'field': 'Type_of_Assistance__c',
            'values': ['Academic', 'Financial'], 'default': 'Academic'})
        assert resp.status_code == 200
        d = resp.get_json()['data']
        assert d['mode'] == 'new-block'
        assert '<picklist>Type_of_Assistance__c</picklist>' in d['xml']

    def test_recordtype_requires_metadata(self, client):
        resp = client.post('/cli/recordtype', json={'rt_xml': 'nope', 'field': 'X__c', 'values': ['A']})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'

    def test_generate_includes_recordtype_snippets(self, client):
        d = client.post('/cli/generate', json={
            'alias': 'DoaneUAT', 'fields': [], 'permset': {}, 'recordtype_name': 'Case.Advisee_Case'
        }).get_json()['data']
        assert 'RecordType:Case.Advisee_Case' in d['recordtype_retrieve']
        assert 'RecordType:Case.Advisee_Case' in d['recordtype_deploy']


class TestRecipes:
    def test_recipes_envelope(self, client):
        resp = client.post('/cli/recipes', json={
            'object': 'Account', 'fields': ['Name', 'SIS_ID__c'], 'alias': 'DoaneUAT'})
        assert resp.status_code == 200
        d = resp.get_json()['data']
        assert d['describe'] == 'sf sobject describe --sobject Account -o DoaneUAT'
        assert 'SELECT Id, Name, SIS_ID__c FROM Account' in d['query']
        assert d['count'] == 'sf data query -o DoaneUAT -q "SELECT COUNT() FROM Account"'
        assert 'CustomObject:Account' in d['retrieve_object']

    def test_recipes_placeholders_when_empty(self, client):
        d = client.post('/cli/recipes', json={}).get_json()['data']
        assert '<Object>' in d['describe'] and '<alias>' in d['describe']


class TestLayout:
    _LAYOUT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n'
              '    <layoutSections>\n'
              '        <label>Case Information</label>\n'
              '        <layoutColumns>\n'
              '            <layoutItems>\n'
              '                <behavior>Edit</behavior>\n'
              '                <field>OwnerId</field>\n'
              '            </layoutItems>\n'
              '        </layoutColumns>\n'
              '        <style>OneColumn</style>\n'
              '    </layoutSections>\n'
              '    <showEmailCheckbox>true</showEmailCheckbox>\n'
              '</Layout>\n')

    def test_layout_sections(self, client):
        resp = client.post('/cli/layout/sections', json={'layout_xml': self._LAYOUT})
        assert resp.status_code == 200
        secs = resp.get_json()['data']['sections']
        assert secs[0]['label'] == 'Case Information' and secs[0]['has_editable_column'] is True

    def test_layout_new_section(self, client):
        resp = client.post('/cli/layout', json={
            'layout_xml': self._LAYOUT, 'new_section': 'Case Assistance',
            'fields': ['Case.Group_Information__c'], 'behavior': 'Edit'})
        assert resp.status_code == 200
        d = resp.get_json()['data']
        assert '<label>Case Assistance</label>' in d['xml']
        assert '<field>Group_Information__c</field>' in d['xml']
        assert d['added'] == ['Group_Information__c']

    def test_layout_requires_layout_xml(self, client):
        resp = client.post('/cli/layout', json={'layout_xml': 'not a layout', 'new_section': 'X',
                                                'fields': ['A__c']})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'

    def test_layout_all_present_is_400(self, client):
        resp = client.post('/cli/layout', json={
            'layout_xml': self._LAYOUT, 'new_section': 'X', 'fields': ['OwnerId']})
        assert resp.status_code == 400  # OwnerId already on the layout

    def test_generate_includes_layout_snippets(self, client):
        d = client.post('/cli/generate', json={
            'alias': 'DoaneUAT', 'fields': [], 'permset': {}, 'layout_name': 'Case-Case Layout'
        }).get_json()['data']
        assert 'Layout:Case-Case Layout' in d['layout_retrieve']
        assert 'Layout:Case-Case Layout' in d['layout_deploy']


class TestPackage:
    def test_package_streams_zip(self, client):
        plan = {
            'project': 'doane-sf', 'alias': 'DoaneUAT',
            'fields': [{'object': 'Account', 'api_name': 'SIS_ID__c', 'label': 'SIS ID',
                        'type': 'Text', 'length': 36, 'externalId': True, 'unique': True}],
            'permset': {},
        }
        resp = client.post('/cli/package', json=plan)
        assert resp.status_code == 200
        assert resp.mimetype == 'application/zip'
        assert 'attachment' in resp.headers['Content-Disposition']
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        assert 'force-app/main/default/objects/Account/fields/SIS_ID__c.field-meta.xml' in zf.namelist()

    def test_package_empty_is_400(self, client):
        resp = client.post('/cli/package', json={'fields': [], 'permset': {}})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_INPUT'

    def test_package_permset_only_for_existing_fields(self, client):
        plan = {'project': 'p', 'alias': 'DoaneUAT', 'fields': [], 'permset': {},
                'human_permset': {'api_name': 'Case_Assistance_Fields', 'editable': True},
                'existing_fields': ['Case.Group_Information__c']}
        resp = client.post('/cli/package', json=plan)
        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        names = zf.namelist()
        assert 'force-app/main/default/permissionsets/Case_Assistance_Fields.permissionset-meta.xml' in names
        # no CustomField files, since no fields were built
        assert not any('/fields/' in n for n in names)
        xml = zf.read('force-app/main/default/permissionsets/Case_Assistance_Fields.permissionset-meta.xml').decode()
        assert '<field>Case.Group_Information__c</field>' in xml

    def test_package_readonly_companion_two_permsets(self, client):
        plan = {'project': 'p', 'alias': 'DoaneUAT', 'fields': [], 'permset': {},
                'human_permset': {'api_name': 'Case_Assistance_Fields', 'editable': True,
                                  'readonly_companion': True},
                'existing_fields': ['Case.Group_Information__c']}
        resp = client.post('/cli/package', json=plan)
        assert resp.status_code == 200
        names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
        assert 'force-app/main/default/permissionsets/Case_Assistance_Fields.permissionset-meta.xml' in names
        assert 'force-app/main/default/permissionsets/Case_Assistance_Fields_ReadOnly.permissionset-meta.xml' in names
        # the companion grants read-only (no edit)
        ro = zipfile.ZipFile(io.BytesIO(resp.data)).read(
            'force-app/main/default/permissionsets/Case_Assistance_Fields_ReadOnly.permissionset-meta.xml').decode()
        assert '<editable>false</editable>' in ro and '<editable>true</editable>' not in ro
