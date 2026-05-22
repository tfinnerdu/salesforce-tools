"""Tests for services.changeset_builder and routes.deploy."""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


# ── Salesforce double ─────────────────────────────────────────────────────────

# Rows keyed by the SOQL fragment that selects them; query_all / restful route
# by the object name appearing in the SOQL string.
_QUERY_ALL_ROWS = {
    'ApexClass': [
        {'Name': 'AccountTriggerHandler', 'LastModifiedDate': '2026-01-01T00:00:00Z'},
        {'Name': 'StudentSyncService', 'LastModifiedDate': '2026-02-01T00:00:00Z'},
    ],
    'ApexTrigger': [
        {'Name': 'AccountTrigger', 'TableEnumOrId': 'Account'},
        {'Name': 'ContactPointEmailTrigger', 'TableEnumOrId': 'ContactPointEmail'},
    ],
    'FlowDefinitionView': [
        {'ApiName': 'Student_Onboarding', 'Label': 'Student Onboarding',
         'ProcessType': 'Flow', 'IsActive': True},
        {'ApiName': 'Lead_Routing', 'Label': 'Lead Routing',
         'ProcessType': 'AutoLaunchedFlow', 'IsActive': False},
    ],
    'PermissionSet': [
        {'Name': 'Migration_Admin', 'Label': 'Migration Admin'},
        {'Name': 'SOQL_Runner', 'Label': 'SOQL Runner'},
    ],
}
_RESTFUL_ROWS = {
    'CustomField': [
        {'DeveloperName': 'SIS_ID', 'EntityDefinition': {'QualifiedApiName': 'Account'}},
        {'DeveloperName': 'Ethos_Guid', 'EntityDefinition': {'QualifiedApiName': 'Account'}},
    ],
    'ValidationRule': [
        {'ValidationName': 'Require_SIS_ID', 'EntityDefinition': {'QualifiedApiName': 'Account'}},
        {'ValidationName': 'Phone_Format', 'EntityDefinition': {'QualifiedApiName': 'ContactPointPhone'}},
    ],
}


def _fake_sf():
    """A Salesforce double serving changeset_builder's query_all / restful calls."""
    sf = MagicMock()

    def query_all(soql):
        for obj, rows in _QUERY_ALL_ROWS.items():
            if f'FROM {obj}' in soql:
                return {'records': rows, 'totalSize': len(rows), 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    def restful(path, params=None):
        q = (params or {}).get('q', '')
        for obj, rows in _RESTFUL_ROWS.items():
            if f'FROM {obj}' in q:
                return {'records': rows, 'totalSize': len(rows), 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    sf.query_all.side_effect = query_all
    sf.restful.side_effect = restful
    return sf


# ── Service unit tests ────────────────────────────────────────────────────────

class TestListComponents:
    """list_components returns correct structure for each metadata type."""

    def _list(self, component_type):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            from services.changeset_builder import list_components
            return list_components('dev', component_type)

    def _check_shape(self, items, expected_type):
        assert isinstance(items, list)
        assert len(items) > 0
        for item in items:
            assert 'member' in item
            assert 'type' in item
            assert 'label' in item
            assert item['type'] == expected_type
            assert item['member']  # non-empty

    def test_apex_class_returns_list(self):
        items = self._list('ApexClass')
        self._check_shape(items, 'ApexClass')

    def test_apex_class_member_has_no_extension(self):
        items = self._list('ApexClass')
        for item in items:
            assert '.' not in item['member']

    def test_apex_trigger_returns_list(self):
        items = self._list('ApexTrigger')
        self._check_shape(items, 'ApexTrigger')

    def test_apex_trigger_label_contains_object(self):
        items = self._list('ApexTrigger')
        # At least one trigger label should mention the sObject
        labels = [item['label'] for item in items]
        assert any('Account' in lbl or 'ContactPoint' in lbl for lbl in labels)

    def test_flow_returns_list(self):
        items = self._list('Flow')
        self._check_shape(items, 'Flow')

    def test_flow_member_is_developer_name(self):
        items = self._list('Flow')
        for item in items:
            # ApiName must not contain spaces
            assert ' ' not in item['member']

    def test_permission_set_returns_list(self):
        items = self._list('PermissionSet')
        self._check_shape(items, 'PermissionSet')

    def test_custom_field_returns_list(self):
        items = self._list('CustomField')
        self._check_shape(items, 'CustomField')

    def test_custom_field_member_format(self):
        items = self._list('CustomField')
        for item in items:
            # member must be ObjectName.FieldName__c
            assert '.' in item['member']
            assert item['member'].endswith('__c')

    def test_validation_rule_returns_list(self):
        items = self._list('ValidationRule')
        self._check_shape(items, 'ValidationRule')

    def test_validation_rule_member_format(self):
        items = self._list('ValidationRule')
        for item in items:
            # member must be ObjectName.RuleName
            assert '.' in item['member']

    def test_unsupported_type_returns_empty(self):
        items = self._list('Profile')
        assert items == []


class TestBuildPackage:
    """build_package produces correct XML and checklist.

    build_package is pure logic — it never touches Salesforce.
    """

    def setup_method(self):
        from services.changeset_builder import build_package
        self.build = build_package

    def _sample_components(self):
        return [
            {'type': 'ApexClass', 'member': 'AccountTriggerHandler'},
            {'type': 'ApexClass', 'member': 'StudentSyncService'},
            {'type': 'CustomField', 'member': 'Account.SIS_ID__c'},
            {'type': 'ValidationRule', 'member': 'Account.Require_SIS_ID_1'},
        ]

    def test_returns_package_xml_key(self):
        result = self.build(self._sample_components())
        assert 'package_xml' in result

    def test_returns_checklist_key(self):
        result = self.build(self._sample_components())
        assert 'checklist' in result

    def test_xml_starts_with_declaration(self):
        result = self.build(self._sample_components())
        assert result['package_xml'].startswith('<?xml version="1.0"')

    def test_xml_contains_package_tag(self):
        xml = self.build(self._sample_components())['package_xml']
        assert '<Package xmlns=' in xml

    def test_xml_contains_api_version(self):
        xml = self.build(self._sample_components(), api_version='65.0')['package_xml']
        assert '<version>65.0</version>' in xml

    def test_xml_members_present(self):
        xml = self.build(self._sample_components())['package_xml']
        assert '<members>AccountTriggerHandler</members>' in xml
        assert '<members>Account.SIS_ID__c</members>' in xml

    def test_xml_type_names_present(self):
        xml = self.build(self._sample_components())['package_xml']
        assert '<name>ApexClass</name>' in xml
        assert '<name>CustomField</name>' in xml

    def test_checklist_grouped_by_type(self):
        result = self.build(self._sample_components())
        type_names = [g['type_name'] for g in result['checklist']]
        assert 'ApexClass' in type_names
        assert 'CustomField' in type_names

    def test_checklist_members_sorted(self):
        result = self.build(self._sample_components())
        for group in result['checklist']:
            members = [m['member'] for m in group['members']]
            assert members == sorted(members)

    def test_checklist_has_setup_path(self):
        result = self.build(self._sample_components())
        for group in result['checklist']:
            for item in group['members']:
                assert 'setup_path' in item
                assert item['setup_path']

    def test_custom_field_setup_path_includes_object(self):
        result = self.build([{'type': 'CustomField', 'member': 'Account.SIS_ID__c'}])
        group = result['checklist'][0]
        item = group['members'][0]
        assert 'Account' in item['setup_path']

    def test_validation_rule_setup_path_includes_object(self):
        result = self.build([{'type': 'ValidationRule', 'member': 'Account.MyRule'}])
        group = result['checklist'][0]
        item = group['members'][0]
        assert 'Account' in item['setup_path']

    def test_apex_class_setup_path(self):
        result = self.build([{'type': 'ApexClass', 'member': 'MyClass'}])
        item = result['checklist'][0]['members'][0]
        assert 'Apex Classes' in item['setup_path']

    def test_empty_components_produces_empty_checklist(self):
        result = self.build([])
        assert result['checklist'] == []
        assert '<version>' in result['package_xml']

    def test_deduplication(self):
        """Duplicate members should appear only once in the output."""
        components = [
            {'type': 'ApexClass', 'member': 'MyClass'},
            {'type': 'ApexClass', 'member': 'MyClass'},
        ]
        result = self.build(components)
        group = result['checklist'][0]
        assert len(group['members']) == 1

    def test_xml_escaping(self):
        """XML special characters in member names must be escaped."""
        components = [{'type': 'ApexClass', 'member': 'A&B<C>'}]
        xml = self.build(components)['package_xml']
        assert '&amp;' in xml or '<members>A&B<C>' not in xml


# ── Route tests ───────────────────────────────────────────────────────────────
#
# These tests use a dedicated minimal Flask app with only the deploy blueprint
# registered, so they do not depend on app.py being updated yet.


@pytest.fixture(scope='module')
def deploy_client():
    """Minimal Flask test client with only the deploy blueprint registered."""
    from routes.deploy import deploy_bp

    mini_app = Flask(__name__, template_folder='../templates')
    mini_app.secret_key = 'test-deploy-secret'
    mini_app.config['TESTING'] = True
    mini_app.register_blueprint(deploy_bp)

    # Provide the context processors that base.html needs
    @mini_app.context_processor
    def _inject():
        return {'sf_instance': ''}

    with mini_app.test_client() as c:
        yield c


class TestDeployRoutes:
    """HTTP-level tests for the deploy blueprint."""

    def test_deploy_index_returns_200(self, deploy_client):
        resp = deploy_client.get('/deploy/')
        assert resp.status_code == 200

    def test_deploy_index_no_slash_returns_200_or_redirect(self, deploy_client):
        resp = deploy_client.get('/deploy')
        assert resp.status_code in (200, 301, 308)

    def test_components_apex_class(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=ApexClass')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['data'], list)
        assert len(data['data']) > 0

    def test_components_apex_trigger(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=ApexTrigger')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_components_custom_field(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=CustomField')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        items = data['data']
        assert len(items) > 0
        assert all('.' in item['member'] for item in items)

    def test_components_flow(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=Flow')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_components_permission_set(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=PermissionSet')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_components_validation_rule(self, deploy_client):
        with patch('services.changeset_builder.get_sf', return_value=_fake_sf()):
            resp = deploy_client.get('/deploy/components?type=ValidationRule')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_components_unsupported_type_returns_400(self, deploy_client):
        resp = deploy_client.get('/deploy/components?type=Profile')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    def test_components_missing_type_returns_400(self, deploy_client):
        resp = deploy_client.get('/deploy/components')
        assert resp.status_code == 400

    def test_generate_returns_package_xml(self, deploy_client):
        payload = {
            'components': [
                {'type': 'ApexClass', 'member': 'AccountTriggerHandler'},
                {'type': 'CustomField', 'member': 'Account.SIS_ID__c'},
            ]
        }
        resp = deploy_client.post('/deploy/generate', json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'package_xml' in data['data']
        assert 'checklist' in data['data']
        assert '<Package' in data['data']['package_xml']

    def test_generate_empty_components_returns_400(self, deploy_client):
        resp = deploy_client.post('/deploy/generate', json={'components': []})
        assert resp.status_code == 400

    def test_generate_no_body_returns_400(self, deploy_client):
        resp = deploy_client.post('/deploy/generate', json={})
        assert resp.status_code == 400

    def test_generate_checklist_has_setup_path(self, deploy_client):
        payload = {
            'components': [
                {'type': 'CustomField', 'member': 'Account.SIS_ID__c'},
            ]
        }
        resp = deploy_client.post('/deploy/generate', json=payload)
        data = resp.get_json()
        checklist = data['data']['checklist']
        assert len(checklist) == 1
        item = checklist[0]['members'][0]
        assert 'Account' in item['setup_path']

    def test_generate_exception_returns_500(self, deploy_client):
        with patch('routes.deploy.changeset_builder.build_package',
                   side_effect=Exception('SF error')):
            payload = {'components': [{'type': 'ApexClass', 'member': 'Foo'}]}
            resp = deploy_client.post('/deploy/generate', json=payload)
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False

    def test_components_exception_returns_500(self, deploy_client):
        with patch('routes.deploy.changeset_builder.list_components',
                   side_effect=Exception('SF down')):
            resp = deploy_client.get('/deploy/components?type=ApexClass')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False
