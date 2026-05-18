"""Tests for services.external_id_coverage."""
import pytest


def test_run_returns_list():
    from services.external_id_coverage import run
    result = run('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_run_includes_all_tracked_objects():
    from services.external_id_coverage import run, TRACKED_OBJECTS
    result = run('dev')
    result_objects = {r['object'] for r in result}
    tracked_objects = {obj for obj, _, _ in TRACKED_OBJECTS}
    assert result_objects == tracked_objects


def test_run_result_structure():
    from services.external_id_coverage import run
    result = run('dev')
    for item in result:
        assert 'object' in item
        assert 'total' in item
        assert 'fields' in item
        assert isinstance(item['fields'], dict)
        for field_name, coverage in item['fields'].items():
            assert 'covered' in coverage
            assert 'total' in coverage
            assert 'pct' in coverage
            assert 'status' in coverage
            assert coverage['status'] in ('green', 'amber', 'red')
            assert 0 <= coverage['pct'] <= 100


def test_account_has_both_external_id_fields():
    from services.external_id_coverage import run
    result = run('dev')
    account = next(r for r in result if r['object'] == 'Account')
    assert 'SIS_ID__c' in account['fields']
    assert 'Ethos_Guid__c' in account['fields']


def test_contactpoint_only_has_sis_id():
    from services.external_id_coverage import run
    result = run('dev')
    cp = next(r for r in result if r['object'] == 'ContactPointEmail')
    assert 'SIS_ID__c' in cp['fields']
    assert 'Ethos_Guid__c' not in cp['fields']


def test_status_thresholds():
    from services.external_id_coverage import run
    result = run('dev')
    account = next(r for r in result if r['object'] == 'Account')
    sis_coverage = account['fields']['SIS_ID__c']
    # mock: 3065/4312 = 71% -> red
    assert sis_coverage['status'] == 'red'
    ethos_coverage = account['fields']['Ethos_Guid__c']
    # mock: 3923/4312 = 91% -> amber or green
    assert ethos_coverage['status'] in ('amber', 'green')


def test_get_missing_records_returns_list():
    from services.external_id_coverage import get_missing_records
    result = get_missing_records('dev', 'Account', 'IsPersonAccount = true', 'SIS_ID__c', limit=10)
    assert isinstance(result, list)
