"""Tests for services.crosswalk_diff.

The fabricated ``_mock_coverage`` helper is gone. ``run_live_check`` now queries
both the EDA and EC side via ``_count_populated`` against the live org, so tests
configure a Salesforce double whose COUNT() queries return controlled numbers.
"""
from unittest.mock import MagicMock, patch

import pytest


def _count(n):
    return {'totalSize': n, 'done': True, 'records': []}


def _sf_counts(count_map, default=0):
    """SF double whose COUNT() queries resolve via substring match in count_map."""
    sf = MagicMock()

    def _query(soql):
        for needle, n in count_map.items():
            if needle in soql:
                return _count(n)
        return _count(default)

    sf.query.side_effect = _query
    return sf


# ── parse_csv (pure logic, unchanged) ─────────────────────────────────────────

def test_parse_csv_basic():
    from services.crosswalk_diff import parse_csv
    csv_text = "eda_object,eda_field,ec_object,ec_field,status\nAccount,Name__c,Account,Name,Mapped\n"
    rows = parse_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]['eda_object'] == 'Account'
    assert rows[0]['status'] == 'Mapped'


def test_parse_csv_strips_whitespace():
    from services.crosswalk_diff import parse_csv
    csv_text = " eda_object , eda_field , status \n Account , Name , Mapped \n"
    rows = parse_csv(csv_text)
    assert rows[0]['eda_object'] == 'Account'
    assert rows[0]['status'] == 'Mapped'


def test_parse_csv_multiple_rows():
    from services.crosswalk_diff import parse_csv
    csv_text = "eda_object,eda_field,ec_object,ec_field,status\nAccount,A,Account,B,Mapped\nAccount,C,Account,D,Unmapped\n"
    rows = parse_csv(csv_text)
    assert len(rows) == 2


def test_parse_csv_keeps_all_rows_including_unmapped():
    from services.crosswalk_diff import parse_csv
    csv_text = "eda_object,ec_object,status\nAccount,Account,Pending\n"
    rows = parse_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]['status'] == 'Pending'


def test_parse_csv_empty_body():
    from services.crosswalk_diff import parse_csv
    csv_text = "eda_object,eda_field\n"
    rows = parse_csv(csv_text)
    assert rows == []


# ── _count_populated ─────────────────────────────────────────────────────────

def test_count_populated_returns_tuple():
    from services.crosswalk_diff import _count_populated
    sf = _sf_counts({'WHERE SIS_ID__c != null': 3000, 'FROM Account': 4312})
    covered, total = _count_populated(sf, 'Account', 'SIS_ID__c')
    assert total == 4312
    assert covered == 3000
    assert 0 <= covered <= total


def test_count_populated_returns_zero_zero_on_exception():
    from services.crosswalk_diff import _count_populated
    sf = MagicMock()
    sf.query.side_effect = Exception("SOQL error")
    covered, total = _count_populated(sf, 'Account', 'SIS_ID__c')
    assert covered == 0
    assert total == 0


def test_count_populated_zero_total_returns_zero_zero():
    from services.crosswalk_diff import _count_populated
    sf = MagicMock()
    sf.query.return_value = {'totalSize': 0, 'done': True, 'records': []}
    covered, total = _count_populated(sf, 'Account', 'SIS_ID__c')
    assert covered == 0
    assert total == 0


# ── run_live_check ────────────────────────────────────────────────────────────

def test_run_live_check_skips_non_mapped_rows():
    from services.crosswalk_diff import run_live_check
    sf = _sf_counts({'FROM Account': 4312})
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Pending'},
        {'eda_object': 'Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Unmapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    assert results == []


def test_run_live_check_skips_rows_with_missing_fields():
    from services.crosswalk_diff import run_live_check
    sf = _sf_counts({'FROM Account': 4312})
    mappings = [
        {'eda_object': 'Account', 'eda_field': '',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
        {'eda_object': '', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    assert results == []


def test_run_live_check_mapped_row_returns_result():
    from services.crosswalk_diff import run_live_check
    sf = _sf_counts({'WHERE SIS_ID__c != null': 3000, 'FROM Account': 4312})
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    assert len(results) == 1
    row = results[0]
    for key in ('eda_object', 'eda_field', 'ec_object', 'ec_field',
                'eda_populated', 'ec_populated', 'total', 'eda_pct', 'ec_pct',
                'gap', 'gap_direction', 'row_status'):
        assert key in row


def test_run_live_check_gap_direction_eda_ahead():
    """EDA side with higher coverage than the EC side -> eda_ahead direction."""
    from services.crosswalk_diff import run_live_check
    sf = MagicMock()

    def _query(soql):
        if 'FROM EDA_Account' in soql and 'WHERE' in soql:
            return _count(970)   # 97%
        if 'FROM EDA_Account' in soql:
            return _count(1000)
        if 'FROM Account' in soql and 'WHERE' in soql:
            return _count(820)   # 82%
        if 'FROM Account' in soql:
            return _count(1000)
        return _count(0)

    sf.query.side_effect = _query
    mappings = [
        {'eda_object': 'EDA_Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    row = results[0]
    assert row['gap_direction'] == 'eda_ahead'
    assert row['eda_pct'] > row['ec_pct']


def test_run_live_check_row_status_warn_when_gap_moderate():
    """EDA 97% vs EC 82% -> 15-point gap -> warn (gap <= 20)."""
    from services.crosswalk_diff import run_live_check
    sf = MagicMock()

    def _query(soql):
        if 'FROM EDA_Account' in soql and 'WHERE' in soql:
            return _count(970)
        if 'FROM EDA_Account' in soql:
            return _count(1000)
        if 'FROM Account' in soql and 'WHERE' in soql:
            return _count(820)
        if 'FROM Account' in soql:
            return _count(1000)
        return _count(0)

    sf.query.side_effect = _query
    mappings = [
        {'eda_object': 'EDA_Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    assert results[0]['row_status'] == 'warn'


def test_run_live_check_row_status_match_when_same():
    """When both sides have identical coverage, gap is 0 -> match."""
    from services.crosswalk_diff import run_live_check
    sf = _sf_counts({'WHERE Name != null': 90, 'FROM Account': 100})
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    row = results[0]
    assert row['gap_direction'] == 'match'
    assert row['row_status'] == 'match'


def test_run_live_check_ec_ahead():
    """EC side with much higher coverage than EDA -> ec_ahead, error (gap > 20)."""
    from services.crosswalk_diff import run_live_check
    sf = MagicMock()

    def _query(soql):
        if 'FROM EDA_Account' in soql and 'WHERE' in soql:
            return _count(500)   # 50%
        if 'FROM EDA_Account' in soql:
            return _count(1000)
        if 'FROM Account' in soql and 'WHERE' in soql:
            return _count(900)   # 90%
        if 'FROM Account' in soql:
            return _count(1000)
        return _count(0)

    sf.query.side_effect = _query
    mappings = [
        {'eda_object': 'EDA_Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    row = results[0]
    assert row['gap_direction'] == 'ec_ahead'
    assert row['row_status'] == 'error'  # 40-point gap > 20


def test_run_live_check_empty_mappings():
    from services.crosswalk_diff import run_live_check
    sf = _sf_counts({})
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', [])
    assert results == []


def test_run_live_check_count_populated_exception_produces_zero_total():
    """If _count_populated raises, row totals are 0 — row still included with 0 pct."""
    from services.crosswalk_diff import run_live_check
    sf = MagicMock()
    sf.query.side_effect = Exception("timeout")
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=sf):
        results = run_live_check('dev', mappings)
    assert len(results) == 1
    row = results[0]
    assert row['eda_pct'] == 0.0
    assert row['ec_pct'] == 0.0
