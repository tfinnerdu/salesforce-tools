"""Tests for services.data_tuner — preview/apply standardization, routes.

Rule-function behavior is pinned by tests/characterization/test_tune_rules_*.
This file covers apply_rules edge cases, record transformation, the
preview/apply pipeline (stubbed and live), and the routes.
"""
import pytest

from services import data_tuner


# ── apply_rules / list_rules ──────────────────────────────────────────────────

def test_apply_rules_none_passthrough():
    assert data_tuner.apply_rules(None, ['trim']) is None


def test_apply_rules_unknown_rule_is_skipped():
    assert data_tuner.apply_rules('  x  ', ['trim', 'no_such_rule']) == 'x'


def test_apply_rules_coerces_non_string():
    assert data_tuner.apply_rules(12345, ['trim']) == '12345'


def test_list_rules_shape():
    rules = data_tuner.list_rules()
    assert isinstance(rules, list) and len(rules) == 8
    assert all('name' in r and 'label' in r for r in rules)


# ── _transform_record ─────────────────────────────────────────────────────────

def test_transform_record_reports_only_changed_fields():
    record = {'Id': '001', 'FirstName': 'JOHN', 'LastName': 'Smith'}
    changes = data_tuner._transform_record(record, {
        'FirstName': ['proper_case'],
        'LastName': ['proper_case'],
    })
    # FirstName JOHN->John changed; LastName Smith already proper
    assert len(changes) == 1
    assert changes[0]['field'] == 'FirstName'
    assert changes[0]['before'] == 'JOHN'
    assert changes[0]['after'] == 'John'


def test_transform_record_skips_blank_values():
    record = {'Id': '001', 'FirstName': '', 'MiddleName': None}
    assert data_tuner._transform_record(record, {
        'FirstName': ['upper'], 'MiddleName': ['upper'],
    }) == []


# ── preview_tune ──────────────────────────────────────────────────────────────

class _StubSF:
    def __init__(self, records, total=None):
        self._records = records
        self._total = total if total is not None else len(records)

    def query(self, soql):
        if 'COUNT()' in soql:
            return {'totalSize': self._total, 'records': []}
        return {'records': self._records}

    def query_all(self, soql):
        return {'records': self._records}


def test_preview_tune_reports_changes(monkeypatch):
    records = [
        {'Id': '001', 'Name': 'JOHN SMITH'},
        {'Id': '002', 'Name': 'Jane Doe'},      # already clean
    ]
    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: _StubSF(records, total=500))
    result = data_tuner.preview_tune('dev', 'Account', 'Id != null', {'Name': ['proper_case']})
    assert result['total_matching'] == 500
    assert result['sample_size'] == 2
    assert result['changed_in_sample'] == 1
    assert result['changed'][0]['id'] == '001'
    assert result['changed'][0]['changes'][0]['after'] == 'John Smith'


def test_preview_tune_requires_field_rules():
    with pytest.raises(ValueError, match='field'):
        data_tuner.preview_tune('dev', 'Account', 'Id != null', {})


# ── apply_tune ────────────────────────────────────────────────────────────────

def test_apply_tune_mock_mode_computes_real_counts(monkeypatch):
    """In mock mode the query+transform runs for real; only the write is skipped."""
    records = [
        {'Id': '001', 'Name': 'JOHN SMITH'},
        {'Id': '002', 'Name': 'BOB JONES'},
        {'Id': '003', 'Name': 'Jane Doe'},     # already clean
    ]
    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: _StubSF(records))
    monkeypatch.setattr(data_tuner.Config, 'SF_MOCK', True)
    result = data_tuner.apply_tune('dev', 'Account', 'Id != null', {'Name': ['proper_case']})
    assert result['mock'] is True
    assert result['updated'] == 2
    assert result['unchanged'] == 1
    assert result['total'] == 3


def test_apply_tune_no_changes_returns_zero(monkeypatch):
    records = [{'Id': '001', 'Name': 'Jane Doe'}]
    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: _StubSF(records))
    monkeypatch.setattr(data_tuner.Config, 'SF_MOCK', True)
    result = data_tuner.apply_tune('dev', 'Account', 'Id != null', {'Name': ['proper_case']})
    assert result['updated'] == 0
    assert result['unchanged'] == 1


def test_apply_tune_requires_field_rules():
    with pytest.raises(ValueError, match='field'):
        data_tuner.apply_tune('dev', 'Account', 'Id != null', {})


# ── apply_tune — real Bulk API 2.0 path ───────────────────────────────────────

class _FakeBulk2Object:
    def __init__(self, processed, failed):
        self._processed = processed
        self._failed = failed
        self.received = None

    def update(self, records=None, **kw):
        self.received = records
        return [{'numberRecordsTotal': len(records),
                 'numberRecordsProcessed': self._processed,
                 'numberRecordsFailed': self._failed,
                 'job_id': 'JOB1'}]


class _FakeBulk2:
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return self._obj


class _LiveSF:
    def __init__(self, records, processed, failed):
        self._records = records
        self.bulk2 = _FakeBulk2(_FakeBulk2Object(processed, failed))

    def query_all(self, soql):
        return {'records': self._records}


def test_apply_tune_live_path_bypass_triggers_toggled(monkeypatch):
    """bypass_triggers must be set before the bulk update and cleared after."""
    calls = []
    import sf_provider
    monkeypatch.setattr(sf_provider, 'set_bypass_triggers',
                        lambda sf, on: calls.append(on))
    sf = _LiveSF([{'Id': '001', 'Name': 'JOHN'}], processed=1, failed=0)
    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: sf)
    monkeypatch.setattr(data_tuner.Config, 'SF_MOCK', False)

    data_tuner.apply_tune('dev', 'Account', 'Id != null',
                          {'Name': ['proper_case']}, bypass_triggers=True)
    assert calls == [True, False]


def test_preview_tune_count_failure_falls_back_to_sample_size(monkeypatch):
    """If the COUNT() query fails, total_matching falls back to the sample size."""
    class _CountFailsSF:
        def query(self, soql):
            if 'COUNT()' in soql:
                raise RuntimeError('count not supported')
            return {'records': [{'Id': '001', 'Name': 'JOHN'}]}

    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: _CountFailsSF())
    result = data_tuner.preview_tune('dev', 'Account', 'Id != null', {'Name': ['proper_case']})
    assert result['total_matching'] == 1
    assert result['changed_in_sample'] == 1


def test_apply_tune_live_path_writes_only_changed_fields(monkeypatch):
    records = [
        {'Id': '001', 'FirstName': 'JOHN', 'LastName': 'SMITH'},
        {'Id': '002', 'FirstName': 'Jane', 'LastName': 'Doe'},   # already clean
    ]
    sf = _LiveSF(records, processed=1, failed=0)
    monkeypatch.setattr(data_tuner, 'get_sf', lambda org: sf)
    monkeypatch.setattr(data_tuner.Config, 'SF_MOCK', False)

    result = data_tuner.apply_tune('dev', 'Account', 'Id != null', {
        'FirstName': ['proper_case'], 'LastName': ['proper_case'],
    })
    assert result['updated'] == 1
    assert result['unchanged'] == 1
    # Only the changed record is sent, carrying just Id + the two normalized fields
    sent = sf.bulk2._obj.received
    assert len(sent) == 1
    assert sent[0]['Id'] == '001'
    assert sent[0]['FirstName'] == 'John'
    assert sent[0]['LastName'] == 'Smith'


# ── Routes ────────────────────────────────────────────────────────────────────

def test_tune_page_renders(client):
    assert client.get('/data-ops/tune').status_code == 200


def test_tune_rules_route(client):
    resp = client.get('/data-ops/tune/rules')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert len(body['data']) == 8


def test_tune_preview_route(client):
    resp = client.post('/data-ops/tune/preview', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'field_rules': {'Name': ['upper']},
    })
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_tune_preview_missing_params_returns_400(client):
    resp = client.post('/data-ops/tune/preview', json={'object': 'Account'})
    assert resp.status_code == 400


def test_tune_execute_route(client):
    resp = client.post('/data-ops/tune/execute', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'field_rules': {'Name': ['upper']},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'updated' in body['data']


def test_tune_execute_missing_params_returns_400(client):
    resp = client.post('/data-ops/tune/execute', json={
        'object': 'Account', 'where_clause': 'Id != null',
    })
    assert resp.status_code == 400


def test_tune_preview_error_returns_500(client, monkeypatch):
    import services.data_tuner as dt
    monkeypatch.setattr(dt, 'preview_tune',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/data-ops/tune/preview', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'field_rules': {'Name': ['upper']},
    })
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
