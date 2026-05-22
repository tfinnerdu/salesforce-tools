"""Tests for services.apex_code_search and /schema/apex-search routes."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _fake_sf(class_records, trigger_records=None, bodies=None):
    """A Salesforce double for apex_code_search.

    ``class_records`` / ``trigger_records`` are the rows query_all returns for
    ApexClass / ApexTrigger.  ``bodies`` maps a record Id to the Apex source
    that the Tooling-API body query returns.
    """
    bodies = bodies or {}
    sf = MagicMock()

    def query_all(soql):
        if 'ApexTrigger' in soql:
            return {'records': trigger_records or [], 'totalSize': len(trigger_records or []),
                    'done': True}
        return {'records': class_records, 'totalSize': len(class_records), 'done': True}

    def restful(path, params=None):
        q = (params or {}).get('q', '')
        # WHERE Id = '<id>'
        for rid, body in bodies.items():
            if f"'{rid}'" in q:
                return {'records': [{'Body': body}], 'totalSize': 1, 'done': True}
        return {'records': [], 'totalSize': 0, 'done': True}

    sf.query_all.side_effect = query_all
    sf.restful.side_effect = restful
    return sf


_CLASS_ROWS = [
    {'Id': '01p000000000001', 'Name': 'StudentSyncService'},
    {'Id': '01p000000000002', 'Name': 'AccountTriggerHandler'},
]
_BODIES = {
    '01p000000000001': "public class StudentSyncService {\n    String x = SIS_ID__c;\n}",
    '01p000000000002': "public class AccountTriggerHandler {\n    // SIS_ID__c lookup\n    update SIS_ID__c;\n}",
}


# ── Service tests ─────────────────────────────────────────────────────────────

def test_search_returns_top_level_keys():
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        from services import apex_code_search
        result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    assert 'pattern' in result
    assert 'matches' in result
    assert 'total_files_searched' in result
    assert 'total_matches' in result


def test_matches_is_a_list():
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        from services import apex_code_search
        result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    assert isinstance(result['matches'], list)


def test_each_match_has_required_keys():
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        from services import apex_code_search
        result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    assert len(result['matches']) > 0
    for m in result['matches']:
        assert 'file_type' in m
        assert 'name' in m
        assert 'line_number' in m
        assert 'line' in m


def test_search_finds_pattern_occurrences_across_files():
    """Every line containing the pattern in every file body becomes a match."""
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        from services import apex_code_search
        result = apex_code_search.search(org='dev', pattern='SIS_ID__c')
    # one hit in StudentSyncService, two in AccountTriggerHandler
    assert result['total_matches'] == 3
    assert len(result['matches']) == 3
    assert result['total_files_searched'] == 2


def test_search_returns_no_matches_when_pattern_absent():
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        from services import apex_code_search
        result = apex_code_search.search(org='dev', pattern='Ethos_Guid__c')
    assert result['total_matches'] == 0
    assert result['matches'] == []


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_apex_search_page_returns_200(client):
    resp = client.get('/schema/apex-search')
    assert resp.status_code == 200


def test_post_apex_search_run_with_pattern_returns_200_success(session_client):
    with patch('services.apex_code_search.get_sf',
               return_value=_fake_sf(_CLASS_ROWS, bodies=_BODIES)):
        resp = session_client.post(
            '/schema/apex-search/run',
            data=json.dumps({'pattern': 'SIS_ID__c'}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'matches' in data['data']
    assert data['data']['total_matches'] == 3


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
