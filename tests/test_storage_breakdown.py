"""Tests for services.storage_breakdown."""
import pytest
from unittest.mock import MagicMock, patch


def _make_sf_mock(count=100):
    sf = MagicMock()
    sf.query.return_value = {'totalSize': count, 'done': True, 'records': []}
    return sf


def test_get_record_counts_returns_list():
    from services.storage_breakdown import get_record_counts
    result = get_record_counts('dev')
    assert isinstance(result, list)


def test_get_record_counts_has_12_objects():
    from services.storage_breakdown import get_record_counts
    result = get_record_counts('dev')
    assert len(result) == 12


def test_get_record_counts_all_objects_present():
    from services.storage_breakdown import get_record_counts
    result = get_record_counts('dev')
    labels = {r['label'] for r in result}
    expected = {
        'Person Accounts',
        'Business Accounts',
        'ContactPoint Emails',
        'ContactPoint Phones',
        'ContactPoint Addresses',
        'Individuals',
        'Campaigns',
        'Campaign Members',
        'Tasks',
        'Events',
        'Cases',
        'Opportunities',
    }
    assert labels == expected


def test_get_record_counts_structure():
    from services.storage_breakdown import get_record_counts
    result = get_record_counts('dev')
    for item in result:
        assert 'object' in item
        assert 'label' in item
        assert 'count' in item


def test_get_record_counts_uses_mock_sf():
    from services.storage_breakdown import get_record_counts
    with patch('services.storage_breakdown.get_sf') as mock_get_sf:
        sf = _make_sf_mock(42)
        mock_get_sf.return_value = sf
        result = get_record_counts('dev')
        assert all(r['count'] == 42 for r in result)
        assert sf.query.call_count == 12


def test_get_record_counts_handles_per_object_exception():
    from services.storage_breakdown import get_record_counts
    with patch('services.storage_breakdown.get_sf') as mock_get_sf:
        sf = MagicMock()
        call_count = [0]

        def side_effect(soql):
            call_count[0] += 1
            if call_count[0] == 3:
                raise Exception('Object not found')
            return {'totalSize': 50, 'done': True, 'records': []}

        sf.query.side_effect = side_effect
        mock_get_sf.return_value = sf
        result = get_record_counts('dev')
        assert len(result) == 12
        # The 3rd item should have count=None and an error key
        errored = [r for r in result if r['count'] is None]
        assert len(errored) == 1
        assert 'error' in errored[0]
