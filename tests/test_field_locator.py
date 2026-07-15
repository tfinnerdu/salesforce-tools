"""Tests for services.field_locator and the /schema/field-finder routes.

The SF client is a MagicMock whose ``restful`` dispatches on the path, so both
the Tooling ``CustomField`` fast path and the describe deep-scan are exercised
without a live org.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services import field_locator as fl


def _fake_sf(custom_records=None, custom_object_records=None,
             describe_global=None, describes=None):
    """SF double dispatching on the Tooling query and the describe path.

    tooling/query → CustomField (``custom_records``) or CustomObject
    (``custom_object_records``); ``sobjects`` → DescribeGlobal; describe → per obj.
    """
    custom_records = custom_records or []
    custom_object_records = custom_object_records or []
    describe_global = describe_global or {'sobjects': []}
    describes = describes or {}
    sf = MagicMock()

    def restful(path, method='GET', **kwargs):
        p = path.lower()
        if 'tooling/query' in p:
            q = ((kwargs.get('params') or {}).get('q') or '').lower()
            if 'from customobject' in q:
                return {'records': custom_object_records}
            return {'records': custom_records}
        if 'sobjects' in p and 'describe' in p:
            obj = path.split('/')[1]
            return describes.get(obj, {'label': obj, 'fields': []})
        if 'sobjects' in p:
            return describe_global
        return {}

    sf.restful.side_effect = restful
    return sf


def _cf(dev, table, namespace=None):
    """A Tooling CustomField record (only the columns the service queries).

    ``table`` is ``TableEnumOrId`` — a standard object's API name or a custom
    object's Id.
    """
    return {'DeveloperName': dev, 'NamespacePrefix': namespace, 'TableEnumOrId': table}


# ── normalize_field_name (pure) ───────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('SIS_ID__c', 'SIS_ID'),
    ('SIS_ID', 'SIS_ID'),
    ('  SIS_ID__c  ', 'SIS_ID'),
    ('hed__Foo__c', 'Foo'),
    ('npsp__Batch__c', 'Batch'),
    ('IsPersonAccount', 'IsPersonAccount'),
    ('Name', 'Name'),
    ('', ''),
])
def test_normalize_field_name(raw, expected):
    assert fl.normalize_field_name(raw) == expected


# ── Tooling fast path ─────────────────────────────────────────────────────────

def test_find_custom_field_across_objects():
    sf = _fake_sf(custom_records=[_cf('SIS_ID', 'Account'),
                                  _cf('SIS_ID', 'ContactPointEmail')])
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'SIS_ID__c')
    assert result['normalized'] == 'SIS_ID'
    assert result['method'] == 'tooling'
    assert result['object_count'] == 2
    assert result['custom_matches'] == 2
    objs = {r['object'] for r in result['results']}
    assert objs == {'Account', 'ContactPointEmail'}
    for r in result['results']:
        assert r['api_name'] == 'SIS_ID__c'
        assert r['custom'] is True


def test_find_filters_non_exact_developer_names():
    # A LIKE-style / unfiltered backend can return extra rows; keep only exact.
    sf = _fake_sf(custom_records=[_cf('SIS_ID', 'Account'),
                                  _cf('SIS_ID_LEGACY', 'Case')])
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'SIS_ID')
    assert result['object_count'] == 1
    assert result['results'][0]['object'] == 'Account'


def test_find_reconstructs_namespaced_api_name():
    sf = _fake_sf(custom_records=[_cf('Foo', 'Account', namespace='hed')])
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'hed__Foo__c')
    row = result['results'][0]
    assert result['normalized'] == 'Foo'
    assert row['api_name'] == 'hed__Foo__c'
    assert row['namespace'] == 'hed'


def test_find_resolves_custom_object_id():
    # A custom field on a CUSTOM object: TableEnumOrId is the object's Id, which
    # a follow-up CustomObject query resolves to its API name (15↔18-char safe).
    sf = _fake_sf(
        custom_records=[_cf('Rating', '01I5g0000012345')],
        custom_object_records=[{'Id': '01I5g0000012345AAB', 'DeveloperName': 'Review',
                                'NamespacePrefix': None}],
    )
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'Rating__c')
    assert result['object_count'] == 1
    assert result['results'][0]['object'] == 'Review__c'
    assert result['results'][0]['api_name'] == 'Rating__c'


def test_find_blank_field_returns_empty():
    sf = _fake_sf()
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', '   ')
    assert result['object_count'] == 0
    assert result['results'] == []


def test_find_custom_only_misses_standard_field():
    # Standard field, no deep scan → the Tooling path finds nothing.
    sf = _fake_sf(custom_records=[])
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'IsPersonAccount')
    assert result['object_count'] == 0
    assert result['method'] == 'tooling'


# ── Deep scan (describe sweep) ────────────────────────────────────────────────

def test_deep_scan_finds_standard_field():
    sf = _fake_sf(
        custom_records=[],
        describe_global={'sobjects': [{'name': 'Account'}, {'name': 'Contact'}]},
        describes={
            'Account': {'label': 'Account', 'fields': [
                {'name': 'IsPersonAccount', 'label': 'Is Person Account',
                 'type': 'boolean', 'custom': False}]},
            'Contact': {'label': 'Contact', 'fields': [
                {'name': 'Email', 'label': 'Email', 'type': 'email', 'custom': False}]},
        })
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'IsPersonAccount', include_standard=True)
    assert result['method'] == 'describe'
    assert result['deep_scanned'] == 2
    assert result['object_count'] == 1
    assert result['standard_matches'] == 1
    row = result['results'][0]
    assert row['object'] == 'Account'
    assert row['type'] == 'boolean'
    assert row['custom'] is False


def test_deep_scan_enriches_tooling_hit_with_type():
    # Custom field found by BOTH paths → one row, type filled in from describe.
    sf = _fake_sf(
        custom_records=[_cf('SIS_ID', 'Account')],
        describe_global={'sobjects': [{'name': 'Account'}]},
        describes={'Account': {'label': 'Account', 'fields': [
            {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string', 'custom': True}]}})
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'SIS_ID__c', include_standard=True)
    assert result['object_count'] == 1
    row = result['results'][0]
    assert row['custom'] is True
    assert row['type'] == 'string'          # enriched from the describe pass


def test_deep_scan_normalizes_namespaced_field_name():
    sf = _fake_sf(
        custom_records=[],
        describe_global={'sobjects': [{'name': 'Course__c'}]},
        describes={'Course__c': {'label': 'Course', 'fields': [
            {'name': 'hed__Foo__c', 'label': 'Foo', 'type': 'string', 'custom': True}]}})
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'Foo', include_standard=True)
    assert result['object_count'] == 1
    assert result['results'][0]['object'] == 'Course__c'


def test_deep_scan_caps_and_flags_truncation(monkeypatch):
    monkeypatch.setattr(fl, 'DEEP_SCAN_MAX_OBJECTS', 2)
    sf = _fake_sf(
        custom_records=[],
        describe_global={'sobjects': [{'name': f'Obj{i}__c'} for i in range(5)]},
        describes={})
    with patch('services.field_locator.get_sf', return_value=sf):
        result = fl.find('dev', 'Whatever', include_standard=True)
    assert result['truncated'] is True
    assert result['deep_scanned'] == 2


# ── Routes ────────────────────────────────────────────────────────────────────

def test_get_field_finder_page_returns_200(client):
    resp = client.get('/schema/field-finder')
    assert resp.status_code == 200


def test_post_field_finder_run_returns_200_success(session_client):
    sf = _fake_sf(custom_records=[_cf('SIS_ID', 'Account')])
    with patch('services.field_locator.get_sf', return_value=sf):
        resp = session_client.post(
            '/api/v1/schema/field-finder/run',
            data=json.dumps({'field': 'SIS_ID__c'}),
            content_type='application/json',
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['object_count'] == 1
    assert data['data']['results'][0]['object'] == 'Account'


def test_post_field_finder_run_without_field_returns_400(client):
    resp = client.post(
        '/api/v1/schema/field-finder/run',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'field required' in data['error']


def test_post_field_finder_run_passes_include_standard(session_client):
    sf = _fake_sf(
        custom_records=[],
        describe_global={'sobjects': [{'name': 'Account'}]},
        describes={'Account': {'label': 'Account', 'fields': [
            {'name': 'IsPersonAccount', 'label': 'Is Person Account',
             'type': 'boolean', 'custom': False}]}})
    with patch('services.field_locator.get_sf', return_value=sf):
        resp = session_client.post(
            '/api/v1/schema/field-finder/run',
            data=json.dumps({'field': 'IsPersonAccount', 'include_standard': True}),
            content_type='application/json',
        )
    data = resp.get_json()['data']
    assert data['method'] == 'describe'
    assert data['object_count'] == 1
