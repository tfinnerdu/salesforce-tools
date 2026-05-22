"""Tests for services.org_automation — validation rules, flows, triggers, sharing model."""
import pytest

from services import org_automation


# ── Stub Salesforce clients ───────────────────────────────────────────────────

_VR_ROWS = [
    {'Id': 'VR1', 'ValidationName': 'Require_SIS', 'Active': True,
     'Description': 'SIS ID required', 'ErrorMessage': 'SIS ID is required',
     'ErrorDisplayField': 'SIS_ID__c',
     'EntityDefinition': {'QualifiedApiName': 'Account'}},
]
_TRIGGER_ROWS = [
    {'Id': 'TR1', 'Name': 'AccountTrigger', 'Status': 'Active', 'ApiVersion': 59.0,
     'LengthWithoutComments': 1200,
     'EntityDefinition': {'QualifiedApiName': 'Account'}},
]
_SHARING_ROWS = [
    {'QualifiedApiName': 'Account', 'Label': 'Account',
     'InternalSharingModel': 'Private', 'ExternalSharingModel': 'Private'},
]
_FLOW_ROWS = [
    {'DurableId': '300A', 'ApiName': 'Sync_Flow', 'Label': 'Sync Flow',
     'ProcessType': 'AutoLaunchedFlow', 'TriggerType': 'RecordAfterSave',
     'IsActive': True, 'Description': 'Sync', 'LastModifiedDate': '2026-01-01'},
]


class _StubSF:
    """SF double returning controlled Tooling (restful) / Data API (query_all) rows."""
    def __init__(self, tooling_rows=None, query_all_rows=None):
        self._tooling = tooling_rows
        self._query_all = query_all_rows

    def restful(self, path, params=None):
        q = (params or {}).get('q', '')
        if self._tooling is not None:
            return {'records': self._tooling}
        if 'ValidationRule' in q:
            return {'records': _VR_ROWS}
        if 'ApexTrigger' in q:
            return {'records': _TRIGGER_ROWS}
        if 'EntityDefinition' in q:
            return {'records': _SHARING_ROWS}
        return {'records': []}

    def query_all(self, soql):
        rows = _FLOW_ROWS if self._query_all is None else self._query_all
        return {'records': rows}


class _RaisingSF:
    def restful(self, *a, **kw):
        raise RuntimeError('tooling api unavailable')

    def query_all(self, *a, **kw):
        raise RuntimeError('data api unavailable')


class _EmptySF:
    """SF stub whose Tooling/Data API queries return no records."""
    def restful(self, *a, **kw):
        return {'records': []}

    def query_all(self, *a, **kw):
        return {'records': []}


# ── Happy path through a stubbed SF Tooling/Data API pipeline ──────────────────

def test_get_validation_rules_returns_list(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    rules = org_automation.get_validation_rules('dev')
    assert isinstance(rules, list)
    assert len(rules) >= 1
    for key in ('id', 'name', 'object', 'active', 'error_message', 'error_field', 'description'):
        assert key in rules[0]


def test_get_flows_returns_list(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    flows = org_automation.get_flows('dev')
    assert isinstance(flows, list)
    assert len(flows) >= 1
    for key in ('id', 'name', 'label', 'type', 'status', 'description', 'last_modified'):
        assert key in flows[0]


def test_get_apex_triggers_returns_list(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    triggers = org_automation.get_apex_triggers('dev')
    assert isinstance(triggers, list)
    assert len(triggers) >= 1
    for key in ('id', 'name', 'object', 'status', 'api_version', 'length'):
        assert key in triggers[0]


def test_get_sharing_model_returns_list(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    rows = org_automation.get_sharing_model('dev')
    assert isinstance(rows, list)
    assert len(rows) >= 1
    for key in ('object', 'label', 'internal', 'internal_label', 'external', 'external_label', 'is_private'):
        assert key in rows[0]


def test_get_sharing_model_translates_private_label(monkeypatch):
    """A Private OWD is flagged is_private and its label is translated."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    rows = org_automation.get_sharing_model('dev')
    account = [r for r in rows if r['object'] == 'Account'][0]
    assert account['is_private'] is True
    assert account['internal_label'] == 'Private'


def test_get_all_has_four_sections(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    data = org_automation.get_all('dev')
    assert set(data.keys()) == {'validation_rules', 'flows', 'triggers', 'sharing_model'}
    for v in data.values():
        assert isinstance(v, list)


# ── Error paths — failures propagate ──────────────────────────────────────────

def test_validation_rules_reraises_on_error(monkeypatch):
    """A tooling-query failure propagates instead of being masked."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        org_automation.get_validation_rules('dev')


def test_flows_reraises_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        org_automation.get_flows('dev')


def test_triggers_reraises_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        org_automation.get_apex_triggers('dev')


def test_sharing_model_reraises_on_error(monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _RaisingSF())
    with pytest.raises(RuntimeError):
        org_automation.get_sharing_model('dev')


# ── Empty-org paths — genuinely empty org returns an empty list ───────────────

@pytest.mark.parametrize('func', [
    'get_validation_rules', 'get_flows', 'get_apex_triggers', 'get_sharing_model',
])
def test_empty_tooling_result_returns_empty(monkeypatch, func):
    """A genuinely empty org returns an empty list — no mock data."""
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _EmptySF())
    assert getattr(org_automation, func)('dev') == []


# ── Route-level tests ─────────────────────────────────────────────────────────

def test_route_validation_rules(client, monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    resp = client.get('/admin/automation/validation-rules')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_flows(client, monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    resp = client.get('/admin/automation/flows')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_triggers(client, monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    resp = client.get('/admin/automation/triggers')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_sharing_model(client, monkeypatch):
    monkeypatch.setattr(org_automation, 'get_sf', lambda org: _StubSF())
    resp = client.get('/admin/automation/sharing-model')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_route_validation_rules_error_returns_500(client, monkeypatch):
    import services.org_automation as oa
    monkeypatch.setattr(oa, 'get_validation_rules', lambda org: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.get('/admin/automation/validation-rules')
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
