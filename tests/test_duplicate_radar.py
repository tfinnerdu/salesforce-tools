"""Tests for services.duplicate_radar."""
from unittest.mock import MagicMock, patch

import pytest


def _fake_sf(records_by_query=None):
    """A Salesforce double whose query_all returns records keyed by a SOQL substring.

    `records_by_query` maps a substring of the SOQL to the records list it should
    return. Anything not matched returns an empty record set.
    """
    records_by_query = records_by_query or {}
    sf = MagicMock()

    def _query_all(soql):
        for needle, recs in records_by_query.items():
            if needle in soql:
                return {'records': recs, 'totalSize': len(recs), 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    sf.query_all.side_effect = _query_all
    return sf


# ── scan ──────────────────────────────────────────────────────────────────────

def test_scan_returns_dict():
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    assert isinstance(result, dict)


def test_scan_has_strategies_key():
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    assert 'strategies' in result
    assert isinstance(result['strategies'], list)
    assert len(result['strategies']) == 5


def test_scan_has_run_at_and_total():
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    assert 'run_at' in result
    assert 'total_groups' in result
    assert isinstance(result['total_groups'], int)


def test_scan_strategy_structure():
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    required = {'strategy', 'label', 'count', 'records', 'status'}
    for strategy in result['strategies']:
        assert required.issubset(strategy.keys()), f"Strategy missing keys: {strategy}"
        assert strategy['status'] in ('green', 'amber', 'red')
        assert isinstance(strategy['count'], int)
        assert isinstance(strategy['records'], list)


def test_scan_strategy_names():
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    names = {s['strategy'] for s in result['strategies']}
    assert 'same_sis_id' in names
    assert 'same_name_dob' in names
    assert 'same_email' in names
    assert 'same_ethos_guid' in names
    assert 'fuzzy_name' in names


def test_scan_status_green_when_no_duplicates():
    """An org with no duplicate records yields all-green strategies."""
    with patch('services.duplicate_radar.get_sf', return_value=_fake_sf()):
        from services.duplicate_radar import scan
        result = scan('dev')
    for strategy in result['strategies']:
        assert strategy['count'] == 0
        assert strategy['status'] == 'green'


def test_scan_detects_duplicate_sis_id():
    """Two PersonAccounts sharing a SIS_ID__c produce one red same_sis_id group."""
    fake = _fake_sf({
        'SIS_ID__c': [
            {'Id': '001A', 'SIS_ID__c': 'S100'},
            {'Id': '001B', 'SIS_ID__c': 'S100'},
        ],
    })
    with patch('services.duplicate_radar.get_sf', return_value=fake):
        from services.duplicate_radar import scan
        result = scan('dev')
    sis = next(s for s in result['strategies'] if s['strategy'] == 'same_sis_id')
    assert sis['count'] == 1
    assert sis['status'] == 'red'
    assert sis['records'][0]['sis_id'] == 'S100'
    assert set(sis['records'][0]['ids']) == {'001A', '001B'}
    assert result['total_groups'] >= 1


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_returns_dict_on_success():
    """merge() returns success=True when sf.Account.merge completes."""
    fake = MagicMock()
    fake.Account.merge.return_value = None
    with patch('services.duplicate_radar.get_sf', return_value=fake), \
         patch('services.merge_history._ensure_table'), \
         patch('services.merge_history.log_merge'):
        from services.duplicate_radar import merge
        result = merge('dev', master_id='001ABC', victim_id='001DEF')
    assert isinstance(result, dict)
    assert result['success'] is True
    assert result['master_id'] == '001ABC'
    assert result['merged_victim_id'] == '001DEF'
    fake.Account.merge.assert_called_once_with('001ABC', ['001DEF'])


def test_merge_reports_failure_when_sf_raises():
    """When sf.Account.merge raises, merge() reports success=False (no fake success)."""
    fake = MagicMock()
    fake.Account.merge.side_effect = RuntimeError('merge rejected')
    with patch('services.duplicate_radar.get_sf', return_value=fake), \
         patch('services.merge_history._ensure_table'), \
         patch('services.merge_history.log_merge'):
        from services.duplicate_radar import merge
        result = merge('dev', master_id='001ABC', victim_id='001DEF')
    assert result['success'] is False
