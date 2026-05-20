"""Tests for services/perm_gap_analyzer.py and its routes."""
import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Unit tests: list_permission_sets
# ---------------------------------------------------------------------------

def test_list_permission_sets_returns_list():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.list_permission_sets('dev')
    assert isinstance(result, list)


def test_list_permission_sets_each_has_required_keys():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.list_permission_sets('dev')
    assert len(result) > 0
    for ps in result:
        assert 'id' in ps
        assert 'name' in ps
        assert 'label' in ps


# ---------------------------------------------------------------------------
# Unit tests: compare
# ---------------------------------------------------------------------------

def test_compare_returns_dict_with_top_level_keys():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.compare('dev', 'a0A000001', 'a0A000002')
    assert isinstance(result, dict)
    for key in ('ps_a', 'ps_b', 'object_gaps', 'field_gaps', 'summary'):
        assert key in result, f"Missing key: {key}"


def test_compare_object_gaps_is_list():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.compare('dev', 'a0A000001', 'a0A000002')
    assert isinstance(result['object_gaps'], list)


def test_compare_object_gaps_items_have_required_keys():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.compare('dev', 'a0A000001', 'a0A000002')
    for gap in result['object_gaps']:
        assert 'object' in gap
        assert 'permission' in gap
        assert 'in_a' in gap
        assert 'in_b' in gap


def test_compare_field_gaps_is_list():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.compare('dev', 'a0A000001', 'a0A000002')
    assert isinstance(result['field_gaps'], list)


def test_compare_summary_has_required_keys():
    from services import perm_gap_analyzer
    result = perm_gap_analyzer.compare('dev', 'a0A000001', 'a0A000002')
    summary = result['summary']
    assert 'only_in_a' in summary
    assert 'only_in_b' in summary
    assert 'total_gaps' in summary


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_perm_gap_list_route_returns_200(client):
    resp = client.get('/impact/perm-gap/list')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_perm_gap_compare_valid_ids_returns_200(client):
    resp = client.post(
        '/impact/perm-gap/compare',
        data=json.dumps({'ps_a': 'a0A000001', 'ps_b': 'a0A000002'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'object_gaps' in data['data']


def test_perm_gap_compare_missing_ps_a_returns_400(client):
    resp = client.post(
        '/impact/perm-gap/compare',
        data=json.dumps({'ps_b': 'a0A000002'}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


def test_perm_gap_compare_same_ids_returns_400(client):
    resp = client.post(
        '/impact/perm-gap/compare',
        data=json.dumps({'ps_a': 'a0A000001', 'ps_b': 'a0A000001'}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'different' in data['error'].lower()


def test_perm_gap_compare_exception_returns_500(client):
    with patch(
        'services.perm_gap_analyzer.compare',
        side_effect=Exception('SF unavailable'),
    ):
        resp = client.post(
            '/impact/perm-gap/compare',
            data=json.dumps({'ps_a': 'a0A000001', 'ps_b': 'a0A000002'}),
            content_type='application/json',
        )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
