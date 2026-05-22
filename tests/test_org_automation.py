"""Tests for services.org_automation — validation rules, flows, triggers, sharing model."""
import pytest

from services import org_automation


# ── Happy path through the mock-SF Tooling API pipeline ───────────────────────

def test_get_validation_rules_returns_list():
    rules = org_automation.get_validation_rules('dev')
    assert isinstance(rules, list)
    assert len(rules) >= 1
    for key in ('id', 'name', 'object', 'active', 'error_message', 'error_field', 'description'):
        assert key in rules[0]


def test_get_flows_returns_list():
    flows = org_automation.get_flows('dev')
    assert isinstance(flows, list)
    assert len(flows) >= 1
    for key in ('id', 'name', 'label', 'type', 'status', 'description', 'last_modified'):
        assert key in flows[0]


def test_get_apex_triggers_returns_list():
    triggers = org_automation.get_apex_triggers('dev')
    assert isinstance(triggers, list)
    assert len(triggers) >= 1
    for key in ('id', 'name', 'object', 'status', 'api_version', 'length'):
        assert key in triggers[0]


def test_get_sharing_model_returns_list():
    rows = org_automation.get_sharing_model('dev')
    assert isinstance(rows, list)
    assert len(rows) >= 1
    for key in ('object', 'label', 'internal', 'internal_label', 'external', 'external_label', 'is_private'):
        assert key in rows[0]


def test_get_all_has_four_sections():
    data = org_automation.get_all('dev')
    assert set(data.keys()) == {'validation_rules', 'flows', 'triggers', 'sharing_model'}
    for v in data.values():
        assert isinstance(v, list)


# ── Mock fallback functions ───────────────────────────────────────────────────

def test_mock_validation_rules_shape():
    rules = org_automation._mock_validation_rules()
    assert len(rules) >= 1
    assert all('active' in r and isinstance(r['active'], bool) for r in rules)


def test_mock_flows_shape():
    flows = org_automation._mock_flows()
    assert len(flows) >= 1
    assert all('status' in f for f in flows)


def test_mock_triggers_shape():
    triggers = org_automation._mock_triggers()
    assert len(triggers) >= 1
    assert all('object' in t for t in triggers)


def test_mock_sharing_model_shape_and_labels():
    rows = org_automation._mock_sharing_model()
    assert len(rows) >= 1
    # Private objects flagged, label translation applied
    private = [r for r in rows if r['object'] == 'Account'][0]
    assert private['is_private'] is True
    assert private['internal_label'] == 'Private'


# ── Fallback / error paths ────────────────────────────────────────────────────

class _RaisingSF:
    def restful(self, *a, **kw):
        raise RuntimeError('tooling api unavailable')

    def query(self, *a, **kw):
        raise RuntimeError('data api unavailable')


def test_validation_rules_falls_back_to_mock_on_error(monkeypatch):
    """With SF_MOCK true, a tooling-query failure returns mock data, not an exception."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    rules = org_automation.get_validation_rules('dev')
    assert isinstance(rules, list)
    assert len(rules) >= 1  # mock fallback


def test_validation_rules_reraises_when_mock_disabled(monkeypatch):
    """With SF_MOCK false, a tooling-query failure propagates instead of masking it."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    monkeypatch.setattr(org_automation.Config, 'SF_MOCK', False)
    with pytest.raises(RuntimeError):
        org_automation.get_validation_rules('dev')


def test_flows_falls_back_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    assert len(org_automation.get_flows('dev')) >= 1


def test_triggers_falls_back_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    assert len(org_automation.get_apex_triggers('dev')) >= 1


def test_sharing_model_falls_back_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    assert len(org_automation.get_sharing_model('dev')) >= 1


class _EmptySF:
    """SF stub whose Tooling/Data API queries return no records."""
    def restful(self, *a, **kw):
        return {'records': []}

    def query(self, *a, **kw):
        return {'records': []}

    def query_all(self, *a, **kw):
        return {'records': []}


@pytest.mark.parametrize('func', [
    'get_validation_rules', 'get_flows', 'get_apex_triggers', 'get_sharing_model',
])
def test_empty_tooling_result_falls_back_to_mock(monkeypatch, func):
    """When a Tooling query returns zero rows and SF_MOCK is on, return mock data."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _EmptySF())
    result = getattr(org_automation, func)('dev')
    assert isinstance(result, list)
    assert len(result) >= 1  # mock fallback kicked in


@pytest.mark.parametrize('func', [
    'get_validation_rules', 'get_flows', 'get_apex_triggers', 'get_sharing_model',
])
def test_empty_tooling_result_returns_empty_when_mock_disabled(monkeypatch, func):
    """With SF_MOCK off, a genuinely empty org returns an empty list — no mock data."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _EmptySF())
    monkeypatch.setattr(org_automation.Config, 'SF_MOCK', False)
    assert getattr(org_automation, func)('dev') == []


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_route_validation_rules(client):
    resp = client.get('/admin/automation/validation-rules')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_flows(client):
    resp = client.get('/admin/automation/flows')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_triggers(client):
    resp = client.get('/admin/automation/triggers')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_sharing_model(client):
    resp = client.get('/admin/automation/sharing-model')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_validation_rules_error_returns_500(client, monkeypatch):
    import services.org_automation as oa
    monkeypatch.setattr(oa, 'get_validation_rules', lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.get('/admin/automation/validation-rules')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
