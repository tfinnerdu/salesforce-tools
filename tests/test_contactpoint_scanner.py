"""Tests for services.contactpoint_scanner."""
import pytest


def test_scan_returns_dict():
    from services.contactpoint_scanner import scan
    result = scan('dev')
    assert isinstance(result, dict)


def test_scan_has_all_contactpoint_types():
    from services.contactpoint_scanner import scan
    result = scan('dev')
    assert 'ContactPointEmail' in result
    assert 'ContactPointPhone' in result
    assert 'ContactPointAddress' in result


def test_scan_has_run_at():
    from services.contactpoint_scanner import scan
    result = scan('dev')
    assert 'run_at' in result
    assert 'total_issues' in result


def test_scan_per_type_structure():
    from services.contactpoint_scanner import scan
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
    result = scan('dev')
    # Mock has broken ContactPoints (ParentId null for idx % 6 == 0)
    has_issues = any(
        result[t]['missing_parent'] > 0
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
    )
    if has_issues:
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            if result[t]['missing_parent'] > 0:
                assert result[t]['status'] == 'red'


def test_scan_total_issues_is_sum():
    from services.contactpoint_scanner import scan
    result = scan('dev')
    expected = sum(
        result[t]['missing_parent'] + result[t]['missing_individual']
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
    )
    assert result['total_issues'] == expected
