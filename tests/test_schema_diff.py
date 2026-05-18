"""Tests for services.schema_diff."""
import pytest


def test_get_object_schema_returns_dict(mock_sf):
    from services.schema_diff import get_object_schema
    schema = get_object_schema(mock_sf, 'Account')
    assert isinstance(schema, dict)
    assert 'Id' in schema
    assert 'SIS_ID__c' in schema


def test_get_object_schema_field_structure(mock_sf):
    from services.schema_diff import get_object_schema
    schema = get_object_schema(mock_sf, 'Account')
    field = schema['SIS_ID__c']
    assert 'type' in field
    assert 'required' in field
    assert 'externalId' in field
    assert field['externalId'] is True


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


def test_run_diff_structure():
    from services.schema_diff import run_diff
    result = run_diff('dev', 'prod', ['Account'])
    assert 'left_org' in result
    assert 'right_org' in result
    assert 'objects' in result
    assert 'Account' in result['objects']


def test_run_diff_uses_default_objects_when_none():
    from services.schema_diff import run_diff, ED_CLOUD_OBJECTS
    result = run_diff('dev', 'prod')
    for obj in ED_CLOUD_OBJECTS:
        assert obj in result['objects']
