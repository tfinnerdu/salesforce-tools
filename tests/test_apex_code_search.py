"""Tests for services.apex_code_search and /schema/apex-search routes."""
import json
import pytest


# ── Service tests ─────────────────────────────────────────────────────────────

def test_search_returns_top_level_keys():
    from services import apex_code_search
    result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    assert 'pattern' in result
    assert 'matches' in result
    assert 'total_files_searched' in result
    assert 'total_matches' in result


def test_matches_is_a_list():
    from services import apex_code_search
    result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    assert isinstance(result['matches'], list)


def test_each_match_has_required_keys():
    from services import apex_code_search
    result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    for m in result['matches']:
        assert 'file_type' in m
        assert 'name' in m
        assert 'line_number' in m
        assert 'line' in m


def test_mock_returns_three_matches_for_any_pattern():
    from services import apex_code_search
    result = apex_code_search.search(org='dev', pattern='anything')
    assert result['total_matches'] == 3
    assert len(result['matches']) == 3


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_apex_search_page_returns_200(client):
    resp = client.get('/schema/apex-search')
    assert resp.status_code == 200


def test_post_apex_search_run_with_pattern_returns_200_success(session_client):
    resp = session_client.post(
        '/schema/apex-search/run',
        data=json.dumps({'pattern': 'SIS_ID__c'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'matches' in data['data']


def test_post_apex_search_run_without_pattern_returns_400(client):
    resp = client.post(
        '/schema/apex-search/run',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'pattern required' in data['error']


def test_post_apex_search_run_with_one_char_pattern_returns_400(client):
    resp = client.post(
        '/schema/apex-search/run',
        data=json.dumps({'pattern': 'x'}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'at least 2 characters' in data['error']
