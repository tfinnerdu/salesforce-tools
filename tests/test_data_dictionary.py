"""Tests for services.data_dictionary and /schema/data-dictionary routes."""
import json
import pytest


# ── Service tests ─────────────────────────────────────────────────────────────

def test_get_field_catalog_returns_top_level_keys():
    from services import data_dictionary
    result = data_dictionary.get_field_catalog(org='dev', sobject='Account')
    assert 'sobject' in result
    assert 'label' in result
    assert 'field_count' in result
    assert 'custom_count' in result
    assert 'fields' in result


def test_fields_is_a_list():
    from services import data_dictionary
    result = data_dictionary.get_field_catalog(org='dev', sobject='Account')
    assert isinstance(result['fields'], list)


def test_each_field_has_required_keys():
    from services import data_dictionary
    result = data_dictionary.get_field_catalog(org='dev', sobject='Account')
    assert len(result['fields']) > 0
    for f in result['fields']:
        assert 'label' in f
        assert 'api_name' in f
        assert 'type' in f
        assert 'custom' in f
        assert 'required' in f


def test_custom_fields_sorted_before_standard():
    from services import data_dictionary
    result = data_dictionary.get_field_catalog(org='dev', sobject='Account')
    fields = result['fields']
    custom_indices = [i for i, f in enumerate(fields) if f['custom']]
    standard_indices = [i for i, f in enumerate(fields) if not f['custom']]
    if custom_indices and standard_indices:
        assert max(custom_indices) < min(standard_indices), \
            "Custom fields should appear before standard fields"


# ── Route tests ───────────────────────────────────────────────────────────────

def test_get_data_dictionary_page_returns_200(client):
    resp = client.get('/schema/data-dictionary')
    assert resp.status_code == 200


def test_post_data_dictionary_run_with_sobject_returns_200_success(session_client):
    resp = session_client.post(
        '/schema/data-dictionary/run',
        data=json.dumps({'sobject': 'Account'}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'fields' in data['data']


def test_post_data_dictionary_run_without_sobject_returns_400(client):
    resp = client.post(
        '/schema/data-dictionary/run',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'sobject required' in data['error']


def test_post_data_dictionary_run_service_exception_returns_500(client, monkeypatch):
    def boom(org, sobject):
        raise RuntimeError('describe exploded')

    import services.data_dictionary as dd_mod
    monkeypatch.setattr(dd_mod, 'get_field_catalog', boom)

    resp = client.post(
        '/schema/data-dictionary/run',
        data=json.dumps({'sobject': 'Account'}),
        content_type='application/json',
    )
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
