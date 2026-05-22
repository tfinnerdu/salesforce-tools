"""Tests for services.external_id_coverage."""
from unittest.mock import MagicMock, patch

import pytest


def _count(n, records=None):
    return {'totalSize': n, 'done': True, 'records': records or []}


def _coverage_sf():
    """SF double driving external_id_coverage.run with controlled counts.

    Account: 4000 total, 2800 SIS_ID (70% -> red), 3640 Ethos_Guid (91% -> amber).
    Other tracked objects: 1000 total with partial coverage.
    """
    sf = MagicMock()

    def _query(soql):
        if 'FROM Account' in soql:
            if 'SIS_ID__c != null' in soql:
                return _count(2800)
            if 'Ethos_Guid__c != null' in soql:
                return _count(3640)
            return _count(4000)
        # ContactPoint* and IndividualApplication
        for obj in ('ContactPointEmail', 'ContactPointPhone',
                    'ContactPointAddress', 'IndividualApplication'):
            if f'FROM {obj}' in soql:
                if '!= null' in soql:
                    return _count(900)
                return _count(1000)
        return _count(0)

    sf.query.side_effect = _query
    return sf


def test_run_returns_list():
    from services.external_id_coverage import run
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
        result = run('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_run_includes_all_tracked_objects():
    from services.external_id_coverage import run, TRACKED_OBJECTS
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
        result = run('dev')
    result_objects = {r['object'] for r in result}
    tracked_objects = {obj for obj, _, _ in TRACKED_OBJECTS}
    assert result_objects == tracked_objects


def test_run_result_structure():
    from services.external_id_coverage import run
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
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
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
        result = run('dev')
    account = next(r for r in result if r['object'] == 'Account')
    assert 'SIS_ID__c' in account['fields']
    assert 'Ethos_Guid__c' in account['fields']


def test_contactpoint_only_has_sis_id():
    from services.external_id_coverage import run
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
        result = run('dev')
    cp = next(r for r in result if r['object'] == 'ContactPointEmail')
    assert 'SIS_ID__c' in cp['fields']
    assert 'Ethos_Guid__c' not in cp['fields']


def test_status_thresholds():
    from services.external_id_coverage import run
    with patch('services.external_id_coverage.get_sf', return_value=_coverage_sf()):
        result = run('dev')
    account = next(r for r in result if r['object'] == 'Account')
    sis_coverage = account['fields']['SIS_ID__c']
    # 2800 / 4000 = 70% -> red
    assert sis_coverage['covered'] == 2800
    assert sis_coverage['total'] == 4000
    assert sis_coverage['status'] == 'red'
    ethos_coverage = account['fields']['Ethos_Guid__c']
    # 3640 / 4000 = 91% -> amber
    assert ethos_coverage['status'] == 'amber'


def test_get_missing_records_returns_list():
    from services.external_id_coverage import get_missing_records
    sf = MagicMock()
    sf.query.return_value = _count(2, records=[
        {'attributes': {'type': 'Account'}, 'Id': '001A', 'Name': 'Alice'},
        {'attributes': {'type': 'Account'}, 'Id': '001B', 'Name': 'Bob'},
    ])
    with patch('services.external_id_coverage.get_sf', return_value=sf):
        result = get_missing_records('dev', 'Account', 'IsPersonAccount = true',
                                     'SIS_ID__c', limit=10)
    assert isinstance(result, list)
    assert len(result) == 2
    # 'attributes' is stripped from each record
    assert all('attributes' not in r for r in result)
    assert result[0]['Id'] == '001A'
