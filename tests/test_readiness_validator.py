"""Tests for services.readiness_validator.

The mock-data layer is gone. Each test builds a Salesforce double whose
``query`` / ``query_all`` answer based on the SOQL string, so the validator's
real logic runs against controlled counts.
"""
from unittest.mock import MagicMock, patch

import pytest


def _count(n):
    return {'totalSize': n, 'done': True, 'records': []}


def _sf_by_soql(count_map, query_all_records=None):
    """Build an SF double: COUNT() queries resolve via substring match in count_map.

    count_map maps a distinguishing SOQL substring -> count. The first matching
    entry wins, so put more-specific substrings first.
    """
    sf = MagicMock()

    def _query(soql):
        for needle, n in count_map.items():
            if needle in soql:
                return _count(n)
        return _count(0)

    sf.query.side_effect = _query
    sf.query_all.return_value = {
        'totalSize': len(query_all_records or []),
        'done': True,
        'records': query_all_records or [],
    }
    return sf


# A controlled org: 4000 PersonAccounts, 2800 with SIS_ID (70% -> red),
# 3640 with Ethos_Guid (91% -> amber).
def _readiness_sf():
    count_map = {
        # specific filters first
        'SIS_ID__c != null': 2800,
        'Ethos_Guid__c != null': 3640,
        'FirstName = null': 20,
        'ContactPointEmail WHERE ParentId = null': 5,
        'ContactPointPhone WHERE ParentId = null': 3,
        'ContactPointAddress WHERE ParentId = null': 2,
        'ContactPointEmail WHERE IndividualId = null': 4,
        'ContactPointPhone WHERE IndividualId = null': 1,
        'ContactPointAddress WHERE IndividualId = null': 0,
        'FROM ContactPointEmail': 1500,
        'FROM ContactPointPhone': 1400,
        'FROM ContactPointAddress': 1300,
        'FROM Account': 4000,
    }
    pa_records = [{'Id': f'001{i:04d}', 'SIS_ID__c': f'STU{i:04d}'} for i in range(50)]
    return _sf_by_soql(count_map, query_all_records=pa_records)


# ── individual checks ─────────────────────────────────────────────────────────

def test_check_sis_id_coverage_returns_dict():
    from services.readiness_validator import check_sis_id_coverage
    result = check_sis_id_coverage(_readiness_sf())
    assert isinstance(result, dict)
    assert 'pct' in result
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')
    assert 0 <= result['pct'] <= 100


def test_check_sis_id_coverage_correct_numbers():
    from services.readiness_validator import check_sis_id_coverage
    result = check_sis_id_coverage(_readiness_sf())
    # 2800 of 4000 = 70% -> red
    assert result['total'] == 4000
    assert result['covered'] == 2800
    assert result['status'] == 'red'


def test_check_ethos_guid_coverage_amber():
    from services.readiness_validator import check_ethos_guid_coverage
    result = check_ethos_guid_coverage(_readiness_sf())
    assert result['total'] == 4000
    # 3640 of 4000 = 91% -> amber
    assert result['status'] == 'amber'


def test_check_contactpoint_parents_returns_broken_count():
    from services.readiness_validator import check_contactpoint_parents
    result = check_contactpoint_parents(_readiness_sf())
    assert 'covered' in result
    assert result['status'] in ('green', 'amber', 'red')
    # 5 + 3 + 2 = 10 broken out of 1500+1400+1300 = 4200 -> 99.76% -> amber
    assert result['total'] == 4200
    assert result['covered'] == 4190


def test_check_required_fields_returns_issues():
    from services.readiness_validator import check_required_fields
    result = check_required_fields(_readiness_sf())
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_check_duplicates_returns_status():
    from services.readiness_validator import check_duplicates
    result = check_duplicates(_readiness_sf())
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


def test_check_duplicates_detects_dup_groups():
    """Two PersonAccounts sharing a SIS_ID surface as one duplicate group."""
    from services.readiness_validator import check_duplicates
    records = [
        {'Id': '001A', 'SIS_ID__c': 'STU001'},
        {'Id': '001B', 'SIS_ID__c': 'STU001'},
        {'Id': '001C', 'SIS_ID__c': 'STU002'},
    ]
    sf = _sf_by_soql({}, query_all_records=records)
    result = check_duplicates(sf)
    # one duplicate group out of 3 -> issue_status amber
    assert result['status'] == 'amber'


def test_check_individual_links_returns_status():
    from services.readiness_validator import check_individual_links
    result = check_individual_links(_readiness_sf())
    assert 'status' in result
    assert result['status'] in ('green', 'amber', 'red')


# ── full readiness check (uses get_sf) ────────────────────────────────────────

def test_run_full_readiness_check_structure():
    from services.readiness_validator import run_full_readiness_check
    with patch('services.readiness_validator.get_sf', return_value=_readiness_sf()):
        result = run_full_readiness_check('dev')
    assert 'checks' in result
    assert 'overall_pct' in result
    assert 'overall_status' in result
    assert 'run_at' in result
    assert isinstance(result['checks'], list)
    assert len(result['checks']) >= 5
    assert 0 <= result['overall_pct'] <= 100
    assert result['overall_status'] in ('green', 'amber', 'red')


def test_run_full_readiness_check_each_check_has_required_keys():
    from services.readiness_validator import run_full_readiness_check
    with patch('services.readiness_validator.get_sf', return_value=_readiness_sf()):
        result = run_full_readiness_check('dev')
    required_keys = {'name', 'status', 'pct'}
    for check in result['checks']:
        assert required_keys.issubset(check.keys()), f"Check missing keys: {check}"


def test_overall_status_is_red_when_any_check_red():
    from services.readiness_validator import run_full_readiness_check
    with patch('services.readiness_validator.get_sf', return_value=_readiness_sf()):
        result = run_full_readiness_check('dev')
    red_checks = [c for c in result['checks'] if c['status'] == 'red']
    # the SIS_ID check is red in this fixture, so overall must be red
    assert red_checks
    assert result['overall_status'] == 'red'


# ── DB persistence helpers (no DB configured) ─────────────────────────────────

def test_save_run_handles_db_error():
    """save_run should not crash when DB is unavailable."""
    from services.readiness_validator import save_run
    result = {'checks': [], 'overall_pct': 75.0, 'overall_status': 'red',
              'run_at': '2026-01-01T00:00:00'}
    save_run('dev', result)


def test_get_history_returns_list_without_db():
    from services.readiness_validator import get_history
    result = get_history('dev', limit=5)
    assert isinstance(result, list)
