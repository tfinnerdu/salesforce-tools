"""Tests for services.duplicate_radar."""
import pytest


def test_scan_returns_dict():
    from services.duplicate_radar import scan
    result = scan('dev')
    assert isinstance(result, dict)


def test_scan_has_strategies_key():
    from services.duplicate_radar import scan
    result = scan('dev')
    assert 'strategies' in result
    assert isinstance(result['strategies'], list)
    assert len(result['strategies']) == 4


def test_scan_has_run_at_and_total():
    from services.duplicate_radar import scan
    result = scan('dev')
    assert 'run_at' in result
    assert 'total_groups' in result
    assert isinstance(result['total_groups'], int)


def test_scan_strategy_structure():
    from services.duplicate_radar import scan
    result = scan('dev')
    required = {'strategy', 'label', 'count', 'records', 'status'}
    for strategy in result['strategies']:
        assert required.issubset(strategy.keys()), f"Strategy missing keys: {strategy}"
        assert strategy['status'] in ('green', 'amber', 'red')
        assert isinstance(strategy['count'], int)
        assert isinstance(strategy['records'], list)


def test_scan_strategy_names():
    from services.duplicate_radar import scan
    result = scan('dev')
    names = {s['strategy'] for s in result['strategies']}
    assert 'same_sis_id' in names
    assert 'same_name_dob' in names
    assert 'same_email' in names
    assert 'same_ethos_guid' in names


def test_scan_status_green_when_no_duplicates():
    from services.duplicate_radar import scan
    result = scan('dev')
    for strategy in result['strategies']:
        if strategy['count'] == 0:
            assert strategy['status'] == 'green'


def test_merge_returns_dict():
    from services.duplicate_radar import merge
    result = merge('dev', master_id='001ABC', victim_id='001DEF')
    assert isinstance(result, dict)
    assert 'success' in result
    assert result['success'] is True
