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
