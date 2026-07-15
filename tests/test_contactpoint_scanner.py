"""Tests for services.contactpoint_scanner."""
from unittest.mock import MagicMock, patch

import pytest


def _count(n, records=None):
    return {'totalSize': n, 'done': True, 'records': records or []}


def _scanner_sf(broken_parent=True, wrong_parent=0):
    """SF double for contactpoint_scanner.

    Per type: total, ParentId-null count, IndividualId-null count,
    wrong-parent-type count (non-null ParentId not prefixed '001'), and the
    matching LIMIT-5 sample queries for each. ``broken_parent`` toggles
    missing-parent/missing-individual; ``wrong_parent`` sets the wrong-type
    count independently (defaults to 0 so existing tests are unaffected).
    """
    sf = MagicMock()
    parents = {'ContactPointEmail': 6, 'ContactPointPhone': 4, 'ContactPointAddress': 2}
    indivs = {'ContactPointEmail': 3, 'ContactPointPhone': 0, 'ContactPointAddress': 1}
    totals = {'ContactPointEmail': 1500, 'ContactPointPhone': 1400, 'ContactPointAddress': 1300}
    wrongs = {'ContactPointEmail': wrong_parent, 'ContactPointPhone': wrong_parent,
             'ContactPointAddress': wrong_parent}

    def _query(soql):
        for cp in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            if f'FROM {cp}' in soql:
                if "NOT ParentId LIKE '001%'" in soql:
                    n = wrongs[cp]
                    if 'LIMIT 5' in soql:
                        sample = [{'Id': f'003{i:015d}'} for i in range(min(n, 5))]
                        return _count(min(n, 5), records=sample)
                    return _count(n)
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
        assert 'wrong_parent_type' in cp
        assert 'total' in cp
        assert 'sample_ids' in cp
        assert 'wrong_parent_sample_ids' in cp
        assert 'status' in cp
        assert cp['status'] in ('green', 'red')
        assert isinstance(cp['sample_ids'], list)
        assert len(cp['sample_ids']) <= 5
        assert isinstance(cp['wrong_parent_sample_ids'], list)
        assert len(cp['wrong_parent_sample_ids']) <= 5


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
        assert result[t]['wrong_parent_type'] == 0
        assert result[t]['status'] == 'green'
    assert result['total_issues'] == 0


# ── wrong-parent-type detection (Ed Cloud invariant: ContactPoint -> Account,
# never Contact) — the load-bearing "known-bad" check CLAUDE.md calls out ────

def test_scan_flags_wrong_parent_type_even_with_no_missing_parents():
    """A ContactPoint that HAS a parent (so missing_parent == 0) but that
    parent is a Contact (id prefix 003, not Account's 001) must be flagged
    red -- this is exactly the case the old missing-parent-only check
    reported as green."""
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf',
               return_value=_scanner_sf(broken_parent=False, wrong_parent=3)):
        result = scan('dev')
    for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
        assert result[t]['missing_parent'] == 0          # not orphaned...
        assert result[t]['wrong_parent_type'] == 3        # ...but wrongly parented
        assert result[t]['status'] == 'red'
    assert result['total_issues'] == 9


def test_scan_wrong_parent_sample_ids_populated():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf',
               return_value=_scanner_sf(broken_parent=False, wrong_parent=2)):
        result = scan('dev')
    for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
        assert len(result[t]['wrong_parent_sample_ids']) == 2
        assert all(sid.startswith('003') for sid in result[t]['wrong_parent_sample_ids'])


def test_scan_wrong_parent_query_shape_characterization():
    """Pins the exact SOQL used to detect a wrongly-parented ContactPoint --
    a non-null ParentId whose id is NOT an Account (001 prefix). If this
    expression drifts, a wrongly-parented ContactPoint could silently stop
    being detected."""
    from services import contactpoint_scanner as mod
    sf = MagicMock()
    sf.query.return_value = _count(0)
    mod._scan_type(sf, 'ContactPointEmail')
    queries = [c.args[0] for c in sf.query.call_args_list]
    assert any(
        "ParentId != null" in q and "NOT ParentId LIKE '001%'" in q
        for q in queries
    ), f'Wrong-parent-type detection query missing or changed shape. Queries seen: {queries}'


def test_scan_total_issues_is_sum():
    from services.contactpoint_scanner import scan
    with patch('services.contactpoint_scanner.get_sf', return_value=_scanner_sf()):
        result = scan('dev')
    expected = sum(
        result[t]['missing_parent'] + result[t]['missing_individual']
        + result[t]['wrong_parent_type']
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
    )
    assert result['total_issues'] == expected
