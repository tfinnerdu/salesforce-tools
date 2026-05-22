"""Tests for services.contactpoint_scanner."""
from unittest.mock import MagicMock, patch

import pytest


def _count(n, records=None):
    return {'totalSize': n, 'done': True, 'records': records or []}


def _scanner_sf(broken_parent=True):
    """SF double for contactpoint_scanner.

    Per type: total, ParentId-null count, IndividualId-null count, and a sample
    Id LIMIT 5 query. ``broken_parent`` toggles whether any links are missing.
    """
    sf = MagicMock()
    parents = {'ContactPointEmail': 6, 'ContactPointPhone': 4, 'ContactPointAddress': 2}
    indivs = {'ContactPointEmail': 3, 'ContactPointPhone': 0, 'ContactPointAddress': 1}
    totals = {'ContactPointEmail': 1500, 'ContactPointPhone': 1400, 'ContactPointAddress': 1300}

    def _query(soql):
        for cp in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            if f'FROM {cp}' in soql:
                if 'LIMIT 5' in soql:
                    n = parents[cp] if broken_parent else 0
                    sample = [{'Id': f'{cp[:3]}{i:04d}'} for i in range(min(n, 5))]
                    return _count(min(n, 5), records=sample)
                if 'ParentId = null' in soql:
                    return _count(parents[cp] if broken_parent else 0)
                if 'IndividualId = null' in soql:
                    return _count(indivs[cp] if broken_parent else 0)
                return _count(totals[cp])
        return _count(0)

    sf.query.side_effect = _query
    return sf


def test_scan_returns_dict():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    assert isinstance(result, dict)


def test_scan_has_all_contactpoint_types():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    assert 'ContactPointEmail' in result
    assert 'ContactPointPhone' in result
    assert 'ContactPointAddress' in result


def test_scan_has_run_at():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    assert 'run_at' in result
    assert 'total_issues' in result


def test_scan_per_type_structure():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    for cp_type in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
        cp = result[cp_type]
        assert 'missing_parent' in cp
        assert 'missing_individual' in cp
        assert 'total' in cp
        assert 'sample_ids' in cp
        assert 'status' in cp
        assert cp['status'] in ('green', 'red')
        assert isinstance(cp['sample_ids'], list)
        assert len(cp['sample_ids']) <= 5


def test_scan_status_red_when_missing_parents():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf(broken_parent=True)):
        result = scan('dev')
    for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
        if result[t]['missing_parent'] > 0:
            assert result[t]['status'] == 'red'


def test_scan_status_green_when_no_issues():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf(broken_parent=False)):
        result = scan('dev')
    for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
        assert result[t]['missing_parent'] == 0
        assert result[t]['status'] == 'green'
    assert result['total_issues'] == 0


def test_scan_total_issues_is_sum():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    expected = sum(
        result[t]['missing_parent'] + result[t]['missing_individual']
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
    )
    assert result['total_issues'] == expected
