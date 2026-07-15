"""Tests for services.audit — the shared AuditEvent dataclass + emit() sink."""
import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from services import audit


class _FakeCursor:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params=None):
        self.store['sql'] = sql
        self.store['params'] = params


@pytest.fixture
def fake_db(monkeypatch):
    store = {}

    @contextmanager
    def fake_cursor():
        yield _FakeCursor(store)

    monkeypatch.setattr(audit, 'get_cursor', fake_cursor)
    return store


# ── AuditEvent shape ──────────────────────────────────────────────────────────

def test_audit_event_has_canonical_fields():
    event = audit.AuditEvent(action='X', actor='y', resource_type='z', resource_id='1',
                             outcome='success')
    assert event.action == 'X'
    assert event.actor == 'y'
    assert event.resource_type == 'z'
    assert event.resource_id == '1'
    assert event.outcome == 'success'
    assert event.detail == {}
    assert event.correlation_id  # auto-generated uuid string
    assert event.occurred_at     # auto-generated ISO timestamp


def test_audit_event_is_frozen():
    event = audit.AuditEvent(action='X', actor='y', resource_type='z', resource_id='1',
                             outcome='success')
    with pytest.raises(Exception):
        event.action = 'changed'


def test_audit_event_default_correlation_ids_are_unique():
    e1 = audit.AuditEvent(action='X', actor='y', resource_type='z', resource_id='1', outcome='success')
    e2 = audit.AuditEvent(action='X', actor='y', resource_type='z', resource_id='1', outcome='success')
    assert e1.correlation_id != e2.correlation_id


# ── current_actor ──────────────────────────────────────────────────────────────

def test_current_actor_outside_request_context_is_system():
    assert audit.current_actor() == 'system'


def test_current_actor_reads_session_user(app):
    with app.test_request_context('/'):
        from flask import session
        session['user'] = 'todd.finner@doane.edu'
        assert audit.current_actor() == 'todd.finner@doane.edu'


def test_current_actor_falls_back_to_system_when_session_user_unset(app):
    with app.test_request_context('/'):
        assert audit.current_actor() == 'system'


# ── emit() ─────────────────────────────────────────────────────────────────────

def test_emit_returns_populated_event(fake_db):
    event = audit.emit('FLS_READ', 'sf_field_permissions', 'dev:Case.Foo__c', 'success',
                       detail={'profiles': 3}, actor='todd')
    assert event.action == 'FLS_READ'
    assert event.actor == 'todd'
    assert event.resource_id == 'dev:Case.Foo__c'
    assert event.detail == {'profiles': 3}


def test_emit_defaults_actor_to_current_actor(fake_db):
    event = audit.emit('X', 'y', 'z', 'success')
    assert event.actor == 'system'


def test_emit_inserts_into_audit_events_table(fake_db):
    audit.emit('FLS_READ', 'sf_field_permissions', 'dev:Case.Foo__c', 'success', actor='todd')
    assert 'INSERT INTO audit_events' in fake_db['sql']
    action, actor, resource_type, resource_id, outcome, detail_json, correlation_id, occurred_at = \
        fake_db['params']
    assert action == 'FLS_READ'
    assert actor == 'todd'
    assert resource_type == 'sf_field_permissions'
    assert resource_id == 'dev:Case.Foo__c'
    assert outcome == 'success'
    assert json.loads(detail_json) == {}


def test_emit_honors_explicit_correlation_id(fake_db):
    event = audit.emit('X', 'y', 'z', 'success', correlation_id='abc-123')
    assert event.correlation_id == 'abc-123'


def test_emit_never_raises_when_db_insert_fails(monkeypatch):
    @contextmanager
    def broken_cursor():
        raise RuntimeError('db down')
        yield  # pragma: no cover

    monkeypatch.setattr(audit, 'get_cursor', broken_cursor)
    # Should not raise even though the DB sink is broken.
    event = audit.emit('X', 'y', 'z', 'success')
    assert event.action == 'X'


def test_emit_logs_structured_json_line(fake_db, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='audit')
    audit.emit('FLS_READ', 'sf_field_permissions', 'dev:Case.Foo__c', 'success', actor='todd')
    assert len(caplog.records) == 1
    logged = json.loads(caplog.records[0].getMessage())
    assert logged['action'] == 'FLS_READ'
    assert logged['actor'] == 'todd'
