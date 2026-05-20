"""Tests for Setup Audit Trail service function and route."""
import pytest


# ── Service: get_audit_trail ───────────────────────────────────────────────────

def test_get_audit_trail_returns_list(mock_sf):
    from services.admin_service import get_audit_trail
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_audit_trail('dev')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_audit_trail_entry_keys(mock_sf):
    from services.admin_service import get_audit_trail
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_audit_trail('dev')
    for entry in result:
        assert 'id' in entry
        assert 'action' in entry
        assert 'section' in entry
        assert 'created_date' in entry
        assert 'created_by' in entry
        assert 'display' in entry


def test_get_audit_trail_sorted_newest_first(mock_sf):
    from services.admin_service import get_audit_trail
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result = get_audit_trail('dev')
    dates = [e['created_date'] for e in result if e['created_date']]
    assert dates == sorted(dates, reverse=True)


def test_get_audit_trail_days_parameter(mock_sf):
    """days parameter is accepted without error; mock always returns all entries."""
    from services.admin_service import get_audit_trail
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('services.admin_service.get_sf', lambda org: mock_sf)
        result_7  = get_audit_trail('dev', days=7)
        result_30 = get_audit_trail('dev', days=30)
    # Mock returns same data regardless of days — just verify both return lists
    assert isinstance(result_7, list)
    assert isinstance(result_30, list)


# ── Routes ─────────────────────────────────────────────────────────────────────

def test_audit_trail_route_200(session_client):
    response = session_client.get('/admin/audit-trail')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_audit_trail_route_days_param(session_client):
    response = session_client.get('/admin/audit-trail?days=14')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_audit_trail_response_data_is_list(session_client):
    response = session_client.get('/admin/audit-trail')
    data = response.get_json()
    assert isinstance(data['data'], list)


def test_audit_trail_exception_returns_500(client):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            'services.admin_service.get_audit_trail',
            lambda org, days=7: (_ for _ in ()).throw(RuntimeError('boom')),
        )
        with client.session_transaction() as sess:
            sess['active_org'] = 'dev'
        response = client.get('/admin/audit-trail')
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
