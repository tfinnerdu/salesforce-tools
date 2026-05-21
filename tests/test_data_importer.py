"""Tests for services.data_importer — CSV import, validation, Bulk API.

Validation logic is exercised with monkeypatched field metadata so every
field type and error path is covered deterministically. The mock-SF pipeline
is used for get_object_fields and import_csv (which short-circuits to mock
results when SF_MOCK is true).
"""
import pytest

from services import data_importer


# ── Controlled field metadata for validation tests ────────────────────────────

def _fields():
    """A controlled set of SF field definitions covering every checked type."""
    return [
        {'name': 'Name',          'type': 'string',   'required': True,  'picklist_values': None},
        {'name': 'Age__c',        'type': 'int',      'required': False, 'picklist_values': None},
        {'name': 'GPA__c',        'type': 'double',   'required': False, 'picklist_values': None},
        {'name': 'EnrollDate__c', 'type': 'date',     'required': False, 'picklist_values': None},
        {'name': 'IsActive__c',   'type': 'boolean',  'required': False, 'picklist_values': None},
        {'name': 'PersonEmail',   'type': 'email',    'required': False, 'picklist_values': None},
        {'name': 'Status__c',     'type': 'picklist', 'required': False,
         'picklist_values': ['Applied', 'Admitted', 'Enrolled']},
    ]


@pytest.fixture
def patched_fields(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_object_fields', lambda org, obj: _fields())


# ── _parse_csv ────────────────────────────────────────────────────────────────

def test_parse_csv_empty_returns_empty_list():
    assert data_importer._parse_csv('') == []


def test_parse_csv_header_only_returns_empty_list():
    assert data_importer._parse_csv('Name,Age__c') == []


def test_parse_csv_parses_rows_into_dicts():
    rows = data_importer._parse_csv('Name,Age__c\nAlice,20\nBob,21')
    assert rows == [{'Name': 'Alice', 'Age__c': '20'}, {'Name': 'Bob', 'Age__c': '21'}]


def test_parse_csv_handles_quoted_commas():
    rows = data_importer._parse_csv('Name,Note\n"Smith, John",hello')
    assert rows[0]['Name'] == 'Smith, John'


# ── validate_csv — clean path ─────────────────────────────────────────────────

def test_validate_clean_rows(patched_fields):
    csv_text = 'Name,Age__c\nAlice,20\nBob,21'
    result = data_importer.validate_csv('dev', 'Account', csv_text,
                                        {'Name': 'Name', 'Age__c': 'Age__c'}, 'insert')
    assert result['total_rows'] == 2
    assert result['clean_rows'] == 2
    assert result['error_rows'] == 0
    assert result['warning_rows'] == 0
    assert result['errors'] == []


def test_validate_empty_csv_returns_zero_counts(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', '', {}, 'insert')
    assert result['total_rows'] == 0
    assert result['clean_rows'] == 0


# ── validate_csv — required field ─────────────────────────────────────────────

def test_validate_required_field_missing_on_insert(patched_fields):
    csv_text = 'Name,Age__c\n,20'
    result = data_importer.validate_csv('dev', 'Account', csv_text,
                                        {'Name': 'Name', 'Age__c': 'Age__c'}, 'insert')
    assert result['error_rows'] == 1
    assert any('Required field' in e['message'] for e in result['errors'])


def test_validate_required_field_skipped_on_update(patched_fields):
    """Required-field check applies only to insert, not update."""
    csv_text = 'Name,Age__c\n,20'
    result = data_importer.validate_csv('dev', 'Account', csv_text,
                                        {'Name': 'Name', 'Age__c': 'Age__c'}, 'update')
    assert result['error_rows'] == 0


# ── validate_csv — type checks ────────────────────────────────────────────────

def test_validate_invalid_integer_is_error(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,Age__c\nAlice,notanumber',
                                        {'Name': 'Name', 'Age__c': 'Age__c'}, 'insert')
    assert result['error_rows'] == 1
    assert any('integer' in e['message'] for e in result['errors'])


def test_validate_invalid_double_is_error(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,GPA__c\nAlice,abc',
                                        {'Name': 'Name', 'GPA__c': 'GPA__c'}, 'insert')
    assert result['error_rows'] == 1
    assert any('number' in e['message'] for e in result['errors'])


def test_validate_bad_date_is_warning(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,EnrollDate__c\nAlice,05/21/2026',
                                        {'Name': 'Name', 'EnrollDate__c': 'EnrollDate__c'}, 'insert')
    assert result['warning_rows'] == 1
    assert result['error_rows'] == 0


def test_validate_bad_boolean_is_warning(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,IsActive__c\nAlice,maybe',
                                        {'Name': 'Name', 'IsActive__c': 'IsActive__c'}, 'insert')
    assert result['warning_rows'] == 1


def test_validate_invalid_email_is_error(patched_fields):
    """Regression: an invalid email used to pass validation as 'clean'.

    SF rejects malformed email-typed fields, so the validator must too.
    """
    result = data_importer.validate_csv('dev', 'Account', 'Name,PersonEmail\nAlice,notanemail',
                                        {'Name': 'Name', 'PersonEmail': 'PersonEmail'}, 'insert')
    assert result['error_rows'] == 1
    assert any('valid email' in e['message'] for e in result['errors'])


def test_validate_good_email_passes(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,PersonEmail\nAlice,alice@doane.edu',
                                        {'Name': 'Name', 'PersonEmail': 'PersonEmail'}, 'insert')
    assert result['error_rows'] == 0


def test_validate_invalid_picklist_is_error(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,Status__c\nAlice,Graduated',
                                        {'Name': 'Name', 'Status__c': 'Status__c'}, 'insert')
    assert result['error_rows'] == 1
    assert any('picklist' in e['message'] for e in result['errors'])


def test_validate_valid_picklist_passes(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,Status__c\nAlice,Admitted',
                                        {'Name': 'Name', 'Status__c': 'Status__c'}, 'insert')
    assert result['error_rows'] == 0


def test_validate_unknown_field_mapping_is_error(patched_fields):
    result = data_importer.validate_csv('dev', 'Account', 'Name,Bogus\nAlice,x',
                                        {'Name': 'Name', 'Bogus': 'NoSuchField__c'}, 'insert')
    assert result['error_rows'] == 1
    assert any('unknown SF field' in e['message'] for e in result['errors'])


def test_validate_summary_aggregates_by_field(patched_fields):
    csv_text = 'Name,Age__c\nA,bad\nB,worse'
    result = data_importer.validate_csv('dev', 'Account', csv_text,
                                        {'Name': 'Name', 'Age__c': 'Age__c'}, 'insert')
    assert 'Age__c' in result['summary']
    assert result['summary']['Age__c']['errors'] == 2


# ── get_object_fields — mock pipeline ─────────────────────────────────────────

def test_get_object_fields_returns_metadata():
    fields = data_importer.get_object_fields('dev', 'Account')
    assert isinstance(fields, list)
    assert len(fields) >= 1
    f = fields[0]
    for key in ('name', 'label', 'type', 'required', 'createable', 'external_id'):
        assert key in f


def test_get_object_fields_describe_failure_raises_valueerror(monkeypatch):
    """A failed describe call is wrapped in a ValueError with the object name."""
    class _BadSF:
        def restful(self, *a, **kw):
            raise RuntimeError('INVALID_TYPE: sObject type not supported')

    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _BadSF())
    with pytest.raises(ValueError, match='NoSuchObject__zzz'):
        data_importer.get_object_fields('dev', 'NoSuchObject__zzz')


# ── import_csv — mock mode ────────────────────────────────────────────────────

def test_import_csv_mock_mode_returns_results():
    csv_text = 'Name,SIS_ID__c\nA,STU1\nB,STU2\nC,STU3'
    result = data_importer.import_csv('dev', 'Account', csv_text,
                                      {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')
    assert result['mock'] is True
    assert result['total'] == result['success_count'] + result['error_count']
    assert result['total'] >= 3


def test_import_csv_mock_has_error_csv_when_failures():
    result = data_importer._mock_import_result(10, 'insert')
    assert result['error_count'] >= 1
    assert result['success_count'] + result['error_count'] == result['total']


def test_mock_import_result_shape():
    result = data_importer._mock_import_result(5, 'upsert')
    assert result['operation'] == 'upsert'
    assert len(result['results']) == result['total']
    assert all('row' in r and 'success' in r for r in result['results'])
