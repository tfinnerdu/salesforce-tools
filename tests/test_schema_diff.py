"""Tests for services.schema_diff."""
from unittest.mock import MagicMock, patch

import pytest


# A describe payload for Account with the fields schema_diff cares about.
_ACCOUNT_DESCRIBE = {
    'name': 'Account',
    'queryable': True,
    'fields': [
        {'name': 'Id', 'label': 'Account ID', 'type': 'id',
         'nillable': False, 'custom': False, 'externalId': False, 'picklistValues': []},
        {'name': 'Name', 'label': 'Account Name', 'type': 'string',
         'nillable': False, 'custom': False, 'externalId': False, 'picklistValues': []},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string',
         'nillable': True, 'custom': True, 'externalId': True, 'picklistValues': []},
        {'name': 'Ethos_Guid__c', 'label': 'Ethos GUID', 'type': 'string',
         'nillable': True, 'custom': True, 'externalId': True, 'picklistValues': []},
        {'name': 'Status__c', 'label': 'Status', 'type': 'picklist',
         'nillable': True, 'custom': True, 'externalId': False,
         'picklistValues': [{'value': 'Active'}, {'value': 'Inactive'}]},
    ],
}


def _fake_sf(describe=None):
    """A Salesforce double whose REST describe returns the given payload."""
    sf = MagicMock()
    sf.restful.return_value = describe if describe is not None else _ACCOUNT_DESCRIBE
    return sf


# ── get_object_schema ─────────────────────────────────────────────────────────

def test_get_object_schema_returns_dict():
    from services.schema_diff import get_object_schema
    schema = get_object_schema(_fake_sf(), 'Account')
    assert isinstance(schema, dict)
    assert 'Id' in schema
    assert 'SIS_ID__c' in schema


def test_get_object_schema_field_structure():
    from services.schema_diff import get_object_schema
    schema = get_object_schema(_fake_sf(), 'Account')
    field = schema['SIS_ID__c']
    assert 'type' in field
    assert 'required' in field
    assert 'externalId' in field
    assert field['externalId'] is True
    # SIS_ID__c is nillable → not required.
    assert field['required'] is False


def test_get_object_schema_requests_describe_path():
    """get_object_schema hits the REST describe endpoint for the named object."""
    from services.schema_diff import get_object_schema
    sf = _fake_sf()
    get_object_schema(sf, 'Account')
    sf.restful.assert_called_once_with('sobjects/Account/describe')


# ── diff_schemas (pure logic) ─────────────────────────────────────────────────

def test_diff_schemas_identical_returns_no_diffs():
    from services.schema_diff import diff_schemas
    schema = {'Id': {'type': 'id', 'required': False, 'picklistValues': [], 'externalId': False}}
    result = diff_schemas(schema, schema)
    assert result['left_only'] == []
    assert result['right_only'] == []
    assert result['type_mismatch'] == []
    assert result['required_mismatch'] == []
    assert result['total_differences'] == 0


def test_diff_schemas_detects_left_only_field():
    from services.schema_diff import diff_schemas
    left = {'Id': {'type': 'id', 'required': False, 'picklistValues': [], 'externalId': False},
            'SIS_ID__c': {'type': 'string', 'required': False, 'picklistValues': [], 'externalId': True}}
    right = {'Id': {'type': 'id', 'required': False, 'picklistValues': [], 'externalId': False}}
    result = diff_schemas(left, right)
    assert 'SIS_ID__c' in result['left_only']


def test_diff_schemas_detects_type_mismatch():
    from services.schema_diff import diff_schemas
    left = {'Name': {'type': 'string', 'required': True, 'picklistValues': [], 'externalId': False}}
    right = {'Name': {'type': 'textarea', 'required': True, 'picklistValues': [], 'externalId': False}}
    result = diff_schemas(left, right)
    assert len(result['type_mismatch']) == 1
    assert result['type_mismatch'][0]['field'] == 'Name'


def test_diff_schemas_detects_required_mismatch():
    from services.schema_diff import diff_schemas
    left = {'Email': {'type': 'email', 'required': True, 'picklistValues': [], 'externalId': False}}
    right = {'Email': {'type': 'email', 'required': False, 'picklistValues': [], 'externalId': False}}
    result = diff_schemas(left, right)
    assert len(result['required_mismatch']) == 1


def test_diff_schemas_detects_picklist_mismatch():
    from services.schema_diff import diff_schemas
    left = {'Status': {'type': 'picklist', 'required': False, 'picklistValues': ['A', 'B'], 'externalId': False}}
    right = {'Status': {'type': 'picklist', 'required': False, 'picklistValues': ['A', 'C'], 'externalId': False}}
    result = diff_schemas(left, right)
    assert len(result['picklist_mismatch']) == 1
    pm = result['picklist_mismatch'][0]
    assert 'B' in pm['left_only_values']
    assert 'C' in pm['right_only_values']


# ── run_diff ──────────────────────────────────────────────────────────────────

def test_run_diff_structure():
    from services.schema_diff import run_diff
    with patch('sf_provider._configured', return_value=True), \
         patch('services.schema_diff.get_sf', return_value=_fake_sf()):
        result = run_diff('dev', 'prod', ['Account'])
    assert 'left_org' in result
    assert 'right_org' in result
    assert 'objects' in result
    assert 'Account' in result['objects']
    # Both orgs describe the same fixture → no differences.
    assert result['objects']['Account']['total_differences'] == 0


def test_run_diff_uses_default_objects_when_none():
    from services.schema_diff import run_diff, ED_CLOUD_OBJECTS
    with patch('sf_provider._configured', return_value=True), \
         patch('services.schema_diff.get_sf', return_value=_fake_sf()):
        result = run_diff('dev', 'prod')
    for obj in ED_CLOUD_OBJECTS:
        assert obj in result['objects']


def test_run_diff_reports_field_differences_between_orgs():
    """When the two orgs' describes differ, run_diff surfaces the diff."""
    from services.schema_diff import run_diff
    # prod is missing SIS_ID__c.
    prod_describe = {
        'name': 'Account', 'queryable': True,
        'fields': [f for f in _ACCOUNT_DESCRIBE['fields'] if f['name'] != 'SIS_ID__c'],
    }
    sf_dev = _fake_sf(_ACCOUNT_DESCRIBE)
    sf_prod = _fake_sf(prod_describe)
    sf_by_org = {'dev': sf_dev, 'prod': sf_prod}
    with patch('sf_provider._configured', return_value=True), \
         patch('services.schema_diff.get_sf', side_effect=lambda o: sf_by_org[o]):
        result = run_diff('dev', 'prod', ['Account'])
    acct = result['objects']['Account']
    assert 'SIS_ID__c' in acct['left_only']
    assert acct['total_differences'] == 1


def test_run_diff_rejects_unconfigured_org():
    """run_diff must raise when an org has no Salesforce credentials configured."""
    from services.schema_diff import run_diff
    # Only 'sandbox' is configured; 'prod' is not.
    with patch('sf_provider._configured', side_effect=lambda org: org == 'sandbox'):
        with pytest.raises(ValueError, match='no Salesforce credentials'):
            run_diff('sandbox', 'prod', ['Account'])
