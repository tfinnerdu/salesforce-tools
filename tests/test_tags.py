"""Tests for services.tags + services.tag_sync scaffold."""
from contextlib import contextmanager

import pytest

from services import tags as svc
from services import tag_sync


# ── In-memory tag store ──────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=None):
        params = params or ()
        s = sql.lower().strip()
        if s.startswith('select id, name, color, created_at from tags'):
            self._result = sorted(self.store['tags'].values(),
                                   key=lambda r: r['name'].lower())
        elif s.startswith('insert into tags'):
            name, color = params
            existing = next((r for r in self.store['tags'].values() if r['name'] == name), None)
            if existing:
                existing['color'] = color
                self._result = existing
            else:
                row = {'id': self.store['next_tag_id'], 'name': name,
                       'color': color, 'created_at': 'now'}
                self.store['tags'][row['id']] = row
                self.store['next_tag_id'] += 1
                self._result = row
        elif s.startswith('delete from tags'):
            tag_id = params[0]
            self.rowcount = 1 if self.store['tags'].pop(tag_id, None) else 0
            # Cascade: drop artifact_tags rows.
            self.store['artifact_tags'] = [
                a for a in self.store['artifact_tags'] if a['tag_id'] != tag_id
            ]
        elif s.startswith('insert into artifact_tags'):
            tag_id, artifact_type, artifact_id = params
            already = any(
                a for a in self.store['artifact_tags']
                if a['tag_id'] == tag_id and a['artifact_type'] == artifact_type
                and a['artifact_id'] == artifact_id
            )
            if not already:
                self.store['artifact_tags'].append({
                    'tag_id': tag_id, 'artifact_type': artifact_type,
                    'artifact_id': artifact_id,
                })
        elif s.startswith('delete from artifact_tags'):
            tag_id, artifact_type, artifact_id = params
            before = len(self.store['artifact_tags'])
            self.store['artifact_tags'] = [
                a for a in self.store['artifact_tags']
                if not (a['tag_id'] == tag_id
                        and a['artifact_type'] == artifact_type
                        and a['artifact_id'] == artifact_id)
            ]
            self.rowcount = before - len(self.store['artifact_tags'])
        elif s.startswith('select t.id, t.name, t.color from tags t join artifact_tags'):
            artifact_type, artifact_id = params
            tag_ids = [
                a['tag_id'] for a in self.store['artifact_tags']
                if a['artifact_type'] == artifact_type and a['artifact_id'] == artifact_id
            ]
            rows = [self.store['tags'][tid] for tid in tag_ids if tid in self.store['tags']]
            self._result = sorted(rows, key=lambda r: r['name'].lower())
        elif s.startswith('select a.artifact_id, t.id, t.name, t.color'):
            artifact_type, artifact_ids = params
            ids = list(artifact_ids)
            out = []
            for a in self.store['artifact_tags']:
                if a['artifact_type'] != artifact_type or a['artifact_id'] not in ids:
                    continue
                t = self.store['tags'].get(a['tag_id'])
                if t:
                    out.append({'artifact_id': a['artifact_id'], 'id': t['id'],
                                'name': t['name'], 'color': t['color']})
            self._result = out
        elif s.startswith('select artifact_id from artifact_tags'):
            artifact_type, tag_id = params
            self._result = [
                {'artifact_id': a['artifact_id']}
                for a in self.store['artifact_tags']
                if a['artifact_type'] == artifact_type and a['tag_id'] == tag_id
            ]

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


@pytest.fixture
def fake_db(monkeypatch):
    store = {'tags': {}, 'artifact_tags': [], 'next_tag_id': 1}

    @contextmanager
    def fake_cursor():
        yield FakeCursor(store)

    monkeypatch.setattr(svc, 'db_available', lambda: True)
    monkeypatch.setattr(svc, 'get_cursor', fake_cursor)
    return store


# ── Tag CRUD ────────────────────────────────────────────────────────────────

class TestTagCRUD:
    def test_create_round_trip(self, fake_db):
        t = svc.create_tag('weekly-cleanup', 'amber')
        assert t['name'] == 'weekly-cleanup'
        assert t['color'] == 'amber'

    def test_create_requires_name(self, fake_db):
        with pytest.raises(ValueError, match='name is required'):
            svc.create_tag('  ')

    def test_create_falls_back_to_slate_for_unknown_color(self, fake_db):
        t = svc.create_tag('x', color='fuchsia')
        assert t['color'] == 'slate'

    def test_list_sorted_alphabetical(self, fake_db):
        svc.create_tag('zeta'); svc.create_tag('alpha'); svc.create_tag('mid')
        assert [t['name'] for t in svc.list_tags()] == ['alpha', 'mid', 'zeta']

    def test_delete_cascades_to_artifact_tags(self, fake_db):
        t = svc.create_tag('to-delete')
        svc.attach_tag(t['id'], 'scenario', 42)
        svc.attach_tag(t['id'], 'scenario', 43)
        assert svc.delete_tag(t['id']) is True
        assert svc.list_tags() == []
        assert svc.get_tags_for('scenario', 42) == []


# ── Attach / detach ──────────────────────────────────────────────────────────

class TestAttachDetach:
    def test_attach_is_idempotent(self, fake_db):
        t = svc.create_tag('a')
        svc.attach_tag(t['id'], 'scenario', 1)
        svc.attach_tag(t['id'], 'scenario', 1)  # second call should not duplicate
        assert len(svc.get_tags_for('scenario', 1)) == 1

    def test_detach_removes(self, fake_db):
        t = svc.create_tag('a')
        svc.attach_tag(t['id'], 'scenario', 1)
        assert svc.detach_tag(t['id'], 'scenario', 1) is True
        assert svc.get_tags_for('scenario', 1) == []

    def test_detach_returns_false_when_not_attached(self, fake_db):
        t = svc.create_tag('a')
        assert svc.detach_tag(t['id'], 'scenario', 999) is False

    def test_rejects_unknown_artifact_type(self, fake_db):
        t = svc.create_tag('a')
        with pytest.raises(ValueError, match='Unknown artifact_type'):
            svc.attach_tag(t['id'], 'sandwich', 1)


# ── Lookups ─────────────────────────────────────────────────────────────────

class TestLookups:
    def test_get_tag_map_batches(self, fake_db):
        a = svc.create_tag('a'); b = svc.create_tag('b')
        svc.attach_tag(a['id'], 'scenario', 1)
        svc.attach_tag(b['id'], 'scenario', 1)
        svc.attach_tag(a['id'], 'scenario', 2)
        m = svc.get_tag_map('scenario', [1, 2])
        assert {t['name'] for t in m[1]} == {'a', 'b'}
        assert {t['name'] for t in m[2]} == {'a'}

    def test_find_artifacts_by_tag(self, fake_db):
        a = svc.create_tag('a')
        svc.attach_tag(a['id'], 'scenario', 11)
        svc.attach_tag(a['id'], 'scenario', 22)
        svc.attach_tag(a['id'], 'saved_query', 33)
        assert sorted(svc.find_artifacts_by_tag('scenario', a['id'])) == [11, 22]
        assert svc.find_artifacts_by_tag('saved_query', a['id']) == [33]


# ── No DB graceful degradation ──────────────────────────────────────────────

class TestNoDb:
    def test_list_returns_empty(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        assert svc.list_tags() == []

    def test_create_raises(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        with pytest.raises(RuntimeError, match='database connection'):
            svc.create_tag('x')


# ── Tag Sync scaffold (option 3, future) ─────────────────────────────────────

class TestTagSyncScaffold:
    def test_sync_available_flag_is_false(self):
        # Future implementer must flip SYNC_AVAILABLE to True after wiring.
        assert tag_sync.SYNC_AVAILABLE is False

    def test_is_configured_follows_config(self, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, 'TAG_SF_FIELD', '')
        assert tag_sync.is_configured() is False
        monkeypatch.setattr(Config, 'TAG_SF_FIELD', 'MC_Tags__c')
        assert tag_sync.is_configured() is True

    def test_sync_to_sf_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match='not yet implemented'):
            tag_sync.sync_tags_to_sf('dev', '001000', ['hello'])

    def test_pull_from_sf_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match='not yet implemented'):
            tag_sync.pull_tags_from_sf('dev', '001000')
