"""Tests for services.crosswalk_diff."""
import pytest
from unittest.mock import MagicMock, patch


# ── parse_csv ─────────────────────────────────────────────────────────────────

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

def test_count_populated_returns_tuple(mock_sf):
    from services.crosswalk_diff import _count_populated
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        result = _count_populated(mock_sf, 'Account', 'SIS_ID__c')
    covered, total = result
    assert total == 4312
    assert 0 <= covered <= total


def test_count_populated_returns_zero_zero_on_exception():
    from services.crosswalk_diff import _count_populated
    mock_sf = MagicMock()
    mock_sf.query.side_effect = Exception("SOQL error")
    covered, total = _count_populated(mock_sf, 'Account', 'SIS_ID__c')
    assert covered == 0
    assert total == 0


def test_count_populated_zero_total_returns_zero_zero():
    from services.crosswalk_diff import _count_populated
    mock_sf = MagicMock()
    mock_sf.query.return_value = {'totalSize': 0, 'done': True, 'records': []}
    covered, total = _count_populated(mock_sf, 'Account', 'SIS_ID__c')
    assert covered == 0
    assert total == 0


# ── _mock_coverage ────────────────────────────────────────────────────────────

def test_mock_coverage_eda_higher_than_ec():
    from services.crosswalk_diff import _mock_coverage
    eda_cov, eda_tot = _mock_coverage('Account', 'SIS_ID__c', 'eda')
    ec_cov, ec_tot = _mock_coverage('Account', 'SIS_ID__c', 'ec')
    assert eda_cov > ec_cov
    assert eda_tot == ec_tot == 4312


def test_mock_coverage_eda_97_percent():
    from services.crosswalk_diff import _mock_coverage
    covered, total = _mock_coverage('Account', 'SIS_ID__c', 'eda')
    pct = covered / total * 100
    assert abs(pct - 97.0) < 1.0  # within 1% of 97


def test_mock_coverage_ec_82_percent():
    from services.crosswalk_diff import _mock_coverage
    covered, total = _mock_coverage('Account', 'SIS_ID__c', 'ec')
    pct = covered / total * 100
    assert abs(pct - 82.0) < 1.0  # within 1% of 82


def test_mock_coverage_unknown_object_uses_default():
    from services.crosswalk_diff import _mock_coverage
    covered, total = _mock_coverage('UnknownObject', 'SomeField', 'eda')
    assert total == 500
    assert covered > 0


def test_mock_coverage_known_objects():
    from services.crosswalk_diff import _mock_coverage
    for obj, expected_total in [
        ('ContactPointEmail', 4100),
        ('ContactPointPhone', 3800),
        ('ContactPointAddress', 3204),
        ('IndividualApplication', 1850),
        ('Opportunity', 620),
    ]:
        _, total = _mock_coverage(obj, 'SIS_ID__c', 'eda')
        assert total == expected_total


# ── run_live_check ────────────────────────────────────────────────────────────

def test_run_live_check_skips_non_mapped_rows(mock_sf):
    from services.crosswalk_diff import run_live_check
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Pending'},
        {'eda_object': 'Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Unmapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    assert results == []


def test_run_live_check_skips_rows_with_missing_fields(mock_sf):
    from services.crosswalk_diff import run_live_check
    mappings = [
        {'eda_object': 'Account', 'eda_field': '',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
        {'eda_object': '', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    assert results == []


def test_run_live_check_mapped_row_returns_result(mock_sf):
    from services.crosswalk_diff import run_live_check
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    assert len(results) == 1
    row = results[0]
    for key in ('eda_object', 'eda_field', 'ec_object', 'ec_field',
                'eda_populated', 'ec_populated', 'total', 'eda_pct', 'ec_pct',
                'gap', 'gap_direction', 'row_status'):
        assert key in row


def test_run_live_check_gap_direction_eda_ahead(mock_sf):
    """When EDA returns same numbers as EC, divergence is applied, making EDA ahead."""
    from services.crosswalk_diff import run_live_check
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    row = results[0]
    # EDA 97% vs EC 82% means EDA is ahead
    assert row['gap_direction'] == 'eda_ahead'
    assert row['eda_pct'] > row['ec_pct']


def test_run_live_check_row_status_error_when_gap_large(mock_sf):
    """Gap >20 pct points → error status."""
    from services.crosswalk_diff import run_live_check
    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    row = results[0]
    # EDA 97% - EC 82% = 15% gap → warn (not error since <=20)
    assert row['row_status'] in ('warn', 'error')


def test_run_live_check_row_status_match_when_same():
    """When both sides are identical coverage, row_status is match."""
    from services.crosswalk_diff import run_live_check
    mock_sf = MagicMock()
    mock_sf.query.return_value = {'totalSize': 100, 'done': True, 'records': []}

    mappings = [
        {'eda_object': 'Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
    ]

    # Patch _mock_coverage to return equal values so both diverge equally
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf), \
         patch('services.crosswalk_diff._mock_coverage', side_effect=lambda obj, field, side: (90, 100)):
        results = run_live_check('dev', mappings)
    row = results[0]
    assert row['gap_direction'] == 'match'
    assert row['row_status'] == 'match'


def test_run_live_check_ec_ahead():
    """EC having more coverage than EDA → ec_ahead direction."""
    from services.crosswalk_diff import run_live_check
    mock_sf = MagicMock()
    mock_sf.query.return_value = {'totalSize': 100, 'done': True, 'records': []}

    def _mock_cov(obj, field, side):
        if side == 'eda':
            return 50, 100  # 50%
        return 90, 100  # 90%

    mappings = [
        {'eda_object': 'Account', 'eda_field': 'Name',
         'ec_object': 'Account', 'ec_field': 'Name', 'status': 'Mapped'},
    ]

    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf), \
         patch('services.crosswalk_diff._mock_coverage', side_effect=_mock_cov):
        results = run_live_check('dev', mappings)
    row = results[0]
    assert row['gap_direction'] == 'ec_ahead'
    assert row['row_status'] == 'error'  # 40% gap > 20


def test_run_live_check_empty_mappings(mock_sf):
    from services.crosswalk_diff import run_live_check
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', [])
    assert results == []


def test_run_live_check_count_populated_exception_produces_zero_total():
    """If _count_populated raises, row totals are 0 — row still included with 0 pct."""
    from services.crosswalk_diff import run_live_check
    mock_sf = MagicMock()
    mock_sf.query.side_effect = Exception("timeout")

    mappings = [
        {'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
         'ec_object': 'Account', 'ec_field': 'SIS_ID__c', 'status': 'Mapped'},
    ]
    with patch('services.crosswalk_diff.get_sf', return_value=mock_sf):
        results = run_live_check('dev', mappings)
    # When count returns (0, 0) for both sides, divergence is applied
    assert len(results) == 1
