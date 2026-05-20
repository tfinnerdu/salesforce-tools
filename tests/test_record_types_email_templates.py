"""Tests for Record Types and Email Templates service functions and routes."""
import pytest


# ── Service: get_record_types ──────────────────────────────────────────────────

def test_get_record_types_returns_list(mock_sf):
    from services.admin_service import get_record_types
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_record_types('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_record_types_required_keys(mock_sf):
    from services.admin_service import get_record_types
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_record_types('dev')
    for rt in result:
        assert 'id' in rt
        assert 'name' in rt
        assert 'developer_name' in rt
        assert 'sobject_type' in rt
        assert 'is_active' in rt
        assert 'record_count' in rt


def test_get_record_types_person_account_present(mock_sf):
    from services.admin_service import get_record_types
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_record_types('dev')
    names = [rt['name'] for rt in result]
    assert 'Person Account' in names


# ── Service: get_email_templates ───────────────────────────────────────────────

def test_get_email_templates_returns_list(mock_sf):
    from services.admin_service import get_email_templates
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_email_templates('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_email_templates_required_keys(mock_sf):
    from services.admin_service import get_email_templates
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_email_templates('dev')
    for t in result:
        assert 'id' in t
        assert 'name' in t
        assert 'folder_name' in t
        assert 'subject' in t
        assert 'is_active' in t


def test_get_email_templates_inactive_present(mock_sf):
    from services.admin_service import get_email_templates
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_email_templates('dev')
    inactive = [t for t in result if not t['is_active']]
    assert len(inactive) > 0


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_record_types_route_200(session_client):
    response = session_client.get('/admin/record-types')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_email_templates_route_200(session_client):
    response = session_client.get('/admin/email-templates')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_record_types_response_is_list(session_client):
    response = session_client.get('/admin/record-types')
    data = response.get_json()
    assert isinstance(data['data'], list)


def test_email_templates_response_is_list(session_client):
    response = session_client.get('/admin/email-templates')
    data = response.get_json()
    assert isinstance(data['data'], list)


def test_record_types_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_record_types', lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/record-types')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False


def test_email_templates_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_email_templates', lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/email-templates')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
