"""Tests for services.data_importer — CSV import, validation, Bulk API.

Validation logic is exercised with monkeypatched field metadata so every
field type and error path is covered deterministically. get_object_fields and
import_csv are exercised against unittest.mock Salesforce doubles.
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


# ── get_object_fields — describe pipeline ─────────────────────────────────────

class _DescribeSF:
    """SF double whose restful() returns a describe payload."""
    def __init__(self, describe):
        self._describe = describe

    def restful(self, path, **kw):
        return self._describe


def test_get_object_fields_returns_metadata(monkeypatch):
    describe = {'fields': [
        {'name': 'Id', 'label': 'Record ID', 'type': 'id',
         'nillable': False, 'createable': False, 'updateable': False, 'externalId': False},
        {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string',
         'nillable': True, 'createable': True, 'updateable': True, 'externalId': True},
    ]}
    monkeypatch.setattr(data_importer, 'get_sf',
                        lambda org: _DescribeSF(describe))
    fields = data_importer.get_object_fields('dev', 'Account')
    assert isinstance(fields, list)
    assert len(fields) == 2
    for key in ('name', 'label', 'type', 'required', 'createable', 'external_id'):
        assert key in fields[0]
    sis = next(f for f in fields if f['name'] == 'SIS_ID__c')
    assert sis['external_id'] is True


def test_get_object_fields_describe_failure_raises_valueerror(monkeypatch):
    """A failed describe call is wrapped in a ValueError with the object name."""
    class _BadSF:
        def restful(self, *a, **kw):
            raise RuntimeError('INVALID_TYPE: sObject type not supported')

    monkeypatch.setattr(data_importer, 'get_sf', lambda org: _BadSF())
    with pytest.raises(ValueError, match='NoSuchObject__zzz'):
        data_importer.get_object_fields('dev', 'NoSuchObject__zzz')


# ── import_csv — bulk2 pipeline ───────────────────────────────────────────────

class _FakeBulk2Object:
    def __init__(self, processed, failed):
        self._processed = processed
        self._failed = failed

    def insert(self, records=None, **kw):
        return [{'numberRecordsTotal': len(records),
                 'numberRecordsProcessed': self._processed,
                 'numberRecordsFailed': self._failed,
                 'job_id': 'JOB1'}]

    def get_failed_records(self, job_id, file=None):
        return ''


class _FakeBulk2:
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return self._obj


class _ImportSF:
    def __init__(self, processed, failed):
        self.bulk2 = _FakeBulk2(_FakeBulk2Object(processed, failed))


def test_import_csv_returns_results(monkeypatch):
    monkeypatch.setattr(data_importer, 'get_sf',
                        lambda org: _ImportSF(processed=3, failed=0))
    csv_text = 'Name,SIS_ID__c\nA,STU1\nB,STU2\nC,STU3'
    result = data_importer.import_csv('dev', 'Account', csv_text,
                                      {'Name': 'Name', 'SIS_ID__c': 'SIS_ID__c'}, 'insert')
    assert result['total'] == result['success_count'] + result['error_count']
    assert result['total'] == 3
    assert result['success_count'] == 3
    assert result['error_count'] == 0
    assert result['operation'] == 'insert'
