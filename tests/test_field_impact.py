"""Tests for services.field_impact — field reference scanner.

Closes a coverage gap found during the TESTING.md matrix reconciliation:
field_impact.py previously had no test of its own.
"""
import pytest

from services import field_impact


# ── Stub Salesforce clients ───────────────────────────────────────────────────

class _StubSF:
    """Returns controlled Tooling/Data API results for scan_field.

    Validation rules come from the Tooling API (restful); flows come from
    FlowDefinitionView on the Data API (query); reports from query_all.
    """
    def __init__(self, validation_rules=None, flows=None, reports=0):
        self._vr = validation_rules or []
        self._flows = flows or []
        self._reports = reports

    def restful(self, path, params=None):
        q = (params or {}).get('q', '')
        if 'ValidationRule' in q:
            return {'records': self._vr}
        return {'records': []}

    def query(self, soql):
        return {'records': []}

    def query_all(self, soql):
        if 'FlowDefinitionView' in soql:
            return {'records': self._flows}
        return {'totalSize': self._reports,
                'records': [{} for _ in range(self._reports)]}


class _RaisingSF:
    def restful(self, *a, **kw):
        raise RuntimeError('tooling api down')

    def query(self, *a, **kw):
        raise RuntimeError('data api down')

    def query_all(self, *a, **kw):
        raise RuntimeError('query api down')


# ── Happy path through the mock-SF pipeline ───────────────────────────────────

def test_scan_field_returns_expected_shape():
    result = field_impact.scan_field('dev', 'Account', 'SIS_ID__c')
    for key in ('object_name', 'field_name', 'validation_rules', 'flows',
                'reports_count', 'summary'):
        assert key in result
    assert result['object_name'] == 'Account'
    assert result['field_name'] == 'SIS_ID__c'
    assert isinstance(result['validation_rules'], list)
    assert isinstance(result['flows'], list)


# ── Controlled results ────────────────────────────────────────────────────────

def test_scan_field_summarizes_found_references(monkeypatch):
    sf = _StubSF(
        validation_rules=[{'Id': 'VR1', 'ValidationName': 'Require_SIS'}],
        flows=[{'Id': 'FL1', 'MasterLabel': 'Sync', 'Status': 'Active'}],
        reports=5,
    )
    monkeypatch.setattr(field_impact, 'get_sf', lambda org: sf)
    result = field_impact.scan_field('dev', 'Account', 'SIS_ID__c')
    assert len(result['validation_rules']) == 1
    assert len(result['flows']) == 1
    assert result['reports_count'] == 5
    assert 'validation rule' in result['summary']
    assert 'flow' in result['summary']
    assert 'report' in result['summary']


def test_scan_field_flows_carry_manual_review_note(monkeypatch):
    sf = _StubSF(flows=[{'Id': 'FL1', 'MasterLabel': 'Sync', 'Status': 'Active'}])
    monkeypatch.setattr(field_impact, 'get_sf', lambda org: sf)
    result = field_impact.scan_field('dev', 'Account', 'SIS_ID__c')
    assert result['flows'][0]['_note']  # manual-review note attached


def test_scan_field_no_references_summary(monkeypatch):
    monkeypatch.setattr(field_impact, 'get_sf', lambda org: _StubSF())
    result = field_impact.scan_field('dev', 'Account', 'Unused_Field__c')
    assert result['validation_rules'] == []
    assert result['flows'] == []
    assert result['reports_count'] == 0
    assert 'No automated references' in result['summary']


# ── Error paths — each query degrades gracefully ──────────────────────────────

def test_scan_field_survives_api_failures(monkeypatch):
    """A Tooling/Data API failure must not crash the scan — it degrades to empty."""
    monkeypatch.setattr(field_impact, 'get_sf', lambda org: _RaisingSF())
    result = field_impact.scan_field('dev', 'Account', 'SIS_ID__c')
    assert result['validation_rules'] == []
    assert result['flows'] == []
    assert result['reports_count'] == 0
    assert 'No automated references' in result['summary']
