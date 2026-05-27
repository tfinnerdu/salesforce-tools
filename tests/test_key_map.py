"""Tests for services.key_map — CRUD + the resolve/fanout engine.

The engine is preview-only in v1 (no writes), but the routing/overlay
behaviour and the FK-resolution caching are the load-bearing pieces — both
are covered here including a PTAT-shaped end-to-end fixture.
"""
import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from config import Config
from services import key_map as svc


# ── In-memory store + cursor double ─────────────────────────────────────────

class _Store:
    def __init__(self):
        self.tables = {
            'key_maps': {},
            'key_map_fk_lookups': {},
            'key_map_families': {},
            'key_map_variants': {},
            'key_map_runs': {},
        }
        self.next_id = {k: 1 for k in self.tables}

    def insert(self, table: str, row: dict) -> dict:
        row = dict(row)
        row['id'] = self.next_id[table]
        self.next_id[table] += 1
        self.tables[table][row['id']] = row
        return row


class FakeCursor:
    def __init__(self, store: _Store):
        self.store = store
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=None):
        params = params or ()
        s = sql.lower().strip()

        if s.startswith('insert into key_maps'):
            name, description, target_sobject, created_by = params
            self._result = self.store.insert('key_maps', {
                'name': name, 'description': description,
                'target_sobject': target_sobject, 'created_by': created_by,
                'created_at': 'now', 'updated_at': 'now',
            })

        elif s.startswith('select id, name, description, target_sobject'):
            if 'where id =' in s:
                self._result = self.store.tables['key_maps'].get(params[0])
            else:
                self._result = sorted(self.store.tables['key_maps'].values(),
                                       key=lambda r: r['name'].lower())

        elif s.startswith('update key_maps'):
            name, description, target_sobject, km_id = params
            row = self.store.tables['key_maps'].get(km_id)
            if row:
                row.update({'name': name, 'description': description,
                            'target_sobject': target_sobject,
                            'updated_at': 'now'})
                self._result = row
                self.rowcount = 1
            else:
                self._result = None

        elif s.startswith('delete from key_maps'):
            self.rowcount = 1 if self.store.tables['key_maps'].pop(params[0], None) else 0

        elif s.startswith('insert into key_map_fk_lookups'):
            km_id, src, tgt, sobj, fld, pos = params
            self._result = self.store.insert('key_map_fk_lookups', {
                'key_map_id': km_id, 'source_column': src, 'target_field': tgt,
                'lookup_sobject': sobj, 'lookup_field': fld, 'position': pos,
            })

        elif s.startswith('select id, key_map_id, source_column, target_field'):
            km_id = params[0]
            rows = [r for r in self.store.tables['key_map_fk_lookups'].values()
                     if r['key_map_id'] == km_id]
            self._result = sorted(rows, key=lambda r: (r['position'], r['id']))

        elif s.startswith('delete from key_map_fk_lookups'):
            self.rowcount = 1 if self.store.tables['key_map_fk_lookups'].pop(params[0], None) else 0

        elif s.startswith('insert into key_map_families'):
            km_id, name, routing_json, pos = params
            self._result = self.store.insert('key_map_families', {
                'key_map_id': km_id, 'name': name,
                'routing_json': json.loads(routing_json),
                'position': pos,
            })

        elif s.startswith('select id, key_map_id, name, routing_json'):
            km_id = params[0]
            rows = [r for r in self.store.tables['key_map_families'].values()
                     if r['key_map_id'] == km_id]
            self._result = sorted(rows, key=lambda r: (r['position'], r['id']))

        elif s.startswith('delete from key_map_families'):
            self.rowcount = 1 if self.store.tables['key_map_families'].pop(params[0], None) else 0

        elif s.startswith('insert into key_map_variants'):
            fam_id, name, overlay_json, applies_when, pos = params
            self._result = self.store.insert('key_map_variants', {
                'family_id': fam_id, 'name': name,
                'overlay_json': json.loads(overlay_json),
                'applies_when': json.loads(applies_when),
                'position': pos,
            })

        elif s.startswith('select id, family_id, name, overlay_json'):
            fam_id = params[0]
            rows = [r for r in self.store.tables['key_map_variants'].values()
                     if r['family_id'] == fam_id]
            self._result = sorted(rows, key=lambda r: (r['position'], r['id']))

        elif s.startswith('delete from key_map_variants'):
            self.rowcount = 1 if self.store.tables['key_map_variants'].pop(params[0], None) else 0

        elif s.startswith('insert into key_map_runs'):
            (km_id, org, status, src_count, out_count,
             unresolved_json, output_json, summary_json) = params
            self._result = self.store.insert('key_map_runs', {
                'key_map_id': km_id, 'org': org, 'status': status,
                'source_count': src_count, 'output_count': out_count,
                'unresolved_fks': json.loads(unresolved_json),
                'output_rows': json.loads(output_json),
                'summary': json.loads(summary_json),
            })

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


@pytest.fixture
def fake_db(monkeypatch):
    store = _Store()

    @contextmanager
    def fake_cursor():
        yield FakeCursor(store)

    monkeypatch.setattr(svc, 'db_available', lambda: True)
    monkeypatch.setattr(svc, 'get_cursor', fake_cursor)
    return store


# ── CRUD basics ──────────────────────────────────────────────────────────────

class TestKeyMapCRUD:
    def test_create_round_trip(self, fake_db):
        km = svc.create_key_map('PTAT v1', 'Desc', 'ProgramTermApplnTimeline')
        assert km['id'] == 1
        assert km['name'] == 'PTAT v1'
        assert km['target_sobject'] == 'ProgramTermApplnTimeline'

    def test_create_requires_name(self, fake_db):
        with pytest.raises(ValueError, match='name is required'):
            svc.create_key_map('  ', '', 'X')

    def test_create_requires_target_sobject(self, fake_db):
        with pytest.raises(ValueError, match='target_sobject'):
            svc.create_key_map('n', '', '')

    def test_update_returns_none_when_missing(self, fake_db):
        assert svc.update_key_map(999, 'x', '', 'Y') is None

    def test_delete_returns_false_when_missing(self, fake_db):
        assert svc.delete_key_map(999) is False

    def test_list_alphabetical(self, fake_db):
        svc.create_key_map('zebra', '', 'X')
        svc.create_key_map('alpha', '', 'X')
        names = [k['name'] for k in svc.list_key_maps()]
        assert names == ['alpha', 'zebra']


class TestFkLookupCRUD:
    def test_add_and_list(self, fake_db):
        km = svc.create_key_map('ptat', '', 'PTAT')
        svc.add_fk_lookup(km['id'], 'TERMS_ID', 'AcademicTermId',
                          'AcademicTerm', position=0)
        svc.add_fk_lookup(km['id'], 'ACAD_PROGRAMS_ID', 'LearningProgramId',
                          'LearningProgram', position=1)
        full = svc.get_key_map(km['id'])
        assert len(full['fk_lookups']) == 2
        assert full['fk_lookups'][0]['target_field'] == 'AcademicTermId'
        assert full['fk_lookups'][1]['lookup_sobject'] == 'LearningProgram'

    def test_add_requires_all_fields(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        with pytest.raises(ValueError, match='source_column'):
            svc.add_fk_lookup(km['id'], '', 'X', 'Y')


class TestFamilyVariantCRUD:
    def test_family_with_routing(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        fam = svc.add_family(km['id'], 'UG',
                             routing={'match': [{'source_column': 'ACPG_ACAD_LEVEL',
                                                 'equals': 'UG'}]})
        assert fam['routing_json']['match'][0]['equals'] == 'UG'

    def test_family_routing_validation_rejects_bad_shape(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        with pytest.raises(ValueError, match='match'):
            svc.add_family(km['id'], 'bad', routing={'match': 'not-a-list'})

    def test_family_routing_validation_rejects_missing_clause_keys(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        with pytest.raises(ValueError, match='source_column'):
            svc.add_family(km['id'], 'bad',
                            routing={'match': [{'source_column': 'X'}]})  # no equals

    def test_variant_overlay(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        fam = svc.add_family(km['id'], 'UG')
        v = svc.add_variant(fam['id'], 'Base',
                            overlay={'APTV': '0PR...', 'Pre': '0PR...A',
                                     'Post': '0PR...B'})
        assert v['overlay_json']['APTV'] == '0PR...'

    def test_variant_overlay_must_be_object(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        fam = svc.add_family(km['id'], 'UG')
        with pytest.raises(ValueError, match='overlay'):
            svc.add_variant(fam['id'], 'bad', overlay='not-a-dict')


# ── Routing logic (internal helpers) ─────────────────────────────────────────

class TestFamilyRouting:
    def test_empty_routing_is_default(self):
        families = [
            {'name': 'UG', 'routing_json': {'match': [
                {'source_column': 'lvl', 'equals': 'UG'}]}, 'variants': []},
            {'name': 'default', 'routing_json': {}, 'variants': []},
        ]
        chosen = svc._family_for_row(families, {'lvl': 'OTHER'})
        assert chosen['name'] == 'default'

    def test_first_matching_family_wins(self):
        families = [
            {'name': 'GR', 'routing_json': {'match': [
                {'source_column': 'lvl', 'equals': 'GR'}]}, 'variants': []},
            {'name': 'UG', 'routing_json': {'match': [
                {'source_column': 'lvl', 'equals': 'UG'}]}, 'variants': []},
            {'name': 'default', 'routing_json': {}, 'variants': []},
        ]
        assert svc._family_for_row(families, {'lvl': 'UG'})['name'] == 'UG'

    def test_multi_clause_routing_is_and(self):
        families = [{'name': 'COE',
                     'routing_json': {'match': [
                         {'source_column': 'lvl', 'equals': 'GR'},
                         {'source_column': 'dept', 'equals': 'COE'}]},
                     'variants': []}]
        assert svc._family_for_row(families, {'lvl': 'GR', 'dept': 'COE'})['name'] == 'COE'
        assert svc._family_for_row(families, {'lvl': 'GR', 'dept': 'OTHER'}) is None

    def test_no_default_no_match_returns_none(self):
        families = [{'name': 'UG',
                     'routing_json': {'match': [
                         {'source_column': 'lvl', 'equals': 'UG'}]},
                     'variants': []}]
        assert svc._family_for_row(families, {'lvl': 'GR'}) is None


# ── End-to-end: a PTAT-shaped expansion ──────────────────────────────────────

class TestResolveAndExpandPTATShape:
    """The flagship case: one source row → multiple PTAT-shaped output rows
    via FK resolution, family routing, and variant overlay."""

    def _build_ptat_key_map(self):
        km = svc.create_key_map('PTAT', '', 'ProgramTermApplnTimeline')
        kid = km['id']
        # Two FK lookups (kept small for test clarity).
        svc.add_fk_lookup(kid, 'TERMS_ID', 'AcademicTermId',
                          'AcademicTerm', 'SIS_ID__c', position=0)
        svc.add_fk_lookup(kid, 'ACAD_PROGRAMS_ID', 'LearningProgramId',
                          'LearningProgram', 'SIS_ID__c', position=1)
        ug = svc.add_family(kid, 'UG',
                            routing={'match': [{'source_column': 'ACPG_ACAD_LEVEL',
                                                'equals': 'UG'}]},
                            position=0)
        gr = svc.add_family(kid, 'GR',
                            routing={'match': [{'source_column': 'ACPG_ACAD_LEVEL',
                                                'equals': 'GR'}]},
                            position=1)
        # UG variants — each is an (APTV, Pre, Post) overlay triple. Dual
        # Credit deliberately omits Pre/Post to exercise partial overlays.
        svc.add_variant(ug['id'], 'Base', overlay={
            'ActionPlanTemplateVersionId': 'APTV_UG',
            'Pre_decision_Requirements_Action_Plan__c': 'PRE_UG',
            'Post_admit_Requirements_Action_Plan__c': 'POST_UG',
        })
        svc.add_variant(ug['id'], 'Transfer', overlay={
            'ActionPlanTemplateVersionId': 'APTV_UG',
            'Pre_decision_Requirements_Action_Plan__c': 'PRE_UG_TRANSFER',
            'Post_admit_Requirements_Action_Plan__c': 'POST_UG_TRANSFER',
        })
        svc.add_variant(ug['id'], 'Dual Credit', overlay={
            # Swap APTV only — pre/post stay as the base UG values from the
            # default. Demonstrates that overlays can be partial.
            'ActionPlanTemplateVersionId': 'APTV_DUAL_CREDIT',
        })
        # GR family with one variant for the routing test.
        svc.add_variant(gr['id'], 'Base', overlay={
            'ActionPlanTemplateVersionId': 'APTV_GR',
            'Pre_decision_Requirements_Action_Plan__c': 'PRE_GR',
            'Post_admit_Requirements_Action_Plan__c': 'POST_GR',
        })
        return kid

    def _fake_sf_with_lookups(self, term_map, program_map):
        """SF double that returns matched records for each IN()-form query."""
        sf = MagicMock()
        def _query(soql):
            if 'FROM AcademicTerm' in soql:
                source = term_map
            elif 'FROM LearningProgram' in soql:
                source = program_map
            else:
                return {'records': []}
            # Pull the IN ('a','b',...) list out of the SOQL.
            inner = soql.split('IN (')[1].split(')')[0]
            wanted = [v.strip().strip("'") for v in inner.split(',')]
            return {
                'records': [
                    {'Id': sf_id, 'SIS_ID__c': key}
                    for key, sf_id in source.items() if key in wanted
                ]
            }
        sf.query.side_effect = _query
        return sf

    def test_one_ug_row_fans_into_three_variants(self, fake_db, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        kid = self._build_ptat_key_map()
        sf = self._fake_sf_with_lookups(
            term_map={'23/AUTM': 'TermId_AUTM'},
            program_map={'ACCT.BA': 'ProgId_ACCT_BA'},
        )
        source_rows = [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'ACCT.BA',
            'ACPG_ACAD_LEVEL': 'UG',
        }]
        result = svc.resolve_and_expand(kid, source_rows, sf_client=sf)
        # One UG source row → 3 UG variants (Base + Transfer + Dual Credit).
        assert result['summary']['output_count'] == 3
        out = result['output_rows']
        # Every output row carries the resolved FK base.
        for row in out:
            assert row['AcademicTermId'] == 'TermId_AUTM'
            assert row['LearningProgramId'] == 'ProgId_ACCT_BA'
        # Variant overlays applied correctly.
        by_variant = {r['_variant']: r for r in out}
        assert by_variant['Base']['Pre_decision_Requirements_Action_Plan__c'] == 'PRE_UG'
        assert by_variant['Transfer']['Pre_decision_Requirements_Action_Plan__c'] == 'PRE_UG_TRANSFER'
        # Dual Credit overlay was partial — APTV swapped, Pre/Post not set
        # (since the overlay was the only source for those keys).
        assert by_variant['Dual Credit']['ActionPlanTemplateVersionId'] == 'APTV_DUAL_CREDIT'
        assert 'Pre_decision_Requirements_Action_Plan__c' not in by_variant['Dual Credit']

    def test_gr_row_routes_to_gr_family(self, fake_db, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        kid = self._build_ptat_key_map()
        sf = self._fake_sf_with_lookups(
            term_map={'23/AUTM': 'TermId_AUTM'},
            program_map={'MBA.MA': 'ProgId_MBA'},
        )
        result = svc.resolve_and_expand(kid, [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'MBA.MA',
            'ACPG_ACAD_LEVEL': 'GR',
        }], sf_client=sf)
        assert result['summary']['output_count'] == 1
        assert result['output_rows'][0]['_family'] == 'GR'
        assert result['output_rows'][0]['ActionPlanTemplateVersionId'] == 'APTV_GR'

    def test_row_with_no_matching_family_is_skipped(self, fake_db, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        kid = self._build_ptat_key_map()
        sf = self._fake_sf_with_lookups(
            term_map={'23/AUTM': 'TermId_AUTM'},
            program_map={'ACCT.BA': 'ProgId_ACCT_BA'},
        )
        result = svc.resolve_and_expand(kid, [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'ACCT.BA',
            'ACPG_ACAD_LEVEL': 'XX',  # neither UG nor GR — no family matches
        }], sf_client=sf)
        assert result['summary']['output_count'] == 0
        assert result['summary']['skipped_no_family'] == 1

    def test_unresolved_fk_surfaces_in_result(self, fake_db, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        kid = self._build_ptat_key_map()
        # ACCT.BA exists in the LearningProgram map; "PHANTOM.BA" doesn't.
        sf = self._fake_sf_with_lookups(
            term_map={'23/AUTM': 'TermId_AUTM'},
            program_map={'ACCT.BA': 'ProgId_ACCT_BA'},
        )
        result = svc.resolve_and_expand(kid, [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'PHANTOM.BA',
            'ACPG_ACAD_LEVEL': 'UG',
        }], sf_client=sf)
        unresolved = result['unresolved_fks']
        assert len(unresolved) == 1
        assert unresolved[0]['source_column'] == 'ACAD_PROGRAMS_ID'
        assert unresolved[0]['value'] == 'PHANTOM.BA'
        # Output rows are still produced — the unresolved column is None.
        assert result['output_rows'][0]['LearningProgramId'] is None

    def test_resolve_and_expand_caches_fk_lookups_across_rows(self, fake_db, monkeypatch):
        """The same LearningProgram value across N rows should only query SF
        once — the engine batches distinct values into a single IN()."""
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        kid = self._build_ptat_key_map()
        sf = self._fake_sf_with_lookups(
            term_map={'23/AUTM': 'TermId_AUTM'},
            program_map={'ACCT.BA': 'ProgId_ACCT_BA'},
        )
        source_rows = [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'ACCT.BA',
            'ACPG_ACAD_LEVEL': 'UG',
        }] * 5  # five identical rows
        svc.resolve_and_expand(kid, source_rows, sf_client=sf)
        # Exactly two SOQL queries: one for AcademicTerm, one for LearningProgram.
        # No per-row repetition.
        assert sf.query.call_count == 2

    def test_show_mock_synthesises_ids_without_sf_call(self, fake_db, monkeypatch):
        """In SHOW_MOCK mode the engine never reaches Salesforce; it
        synthesises stable MOCK_<sobject>_<value> Ids instead so the preview
        stays end-to-end runnable for demos."""
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        kid = self._build_ptat_key_map()
        sf = MagicMock()
        # If the engine reaches for sf in mock mode, this test fails.
        result = svc.resolve_and_expand(kid, [{
            'TERMS_ID': '23/AUTM',
            'ACAD_PROGRAMS_ID': 'ACCT.BA',
            'ACPG_ACAD_LEVEL': 'UG',
        }], sf_client=sf)
        sf.query.assert_not_called()
        # Synthesised Ids are deterministic for stable demo data.
        out = result['output_rows'][0]
        assert out['AcademicTermId'] == 'MOCK_AcademicTerm_23/AUTM'
        assert out['LearningProgramId'] == 'MOCK_LearningProgram_ACCT.BA'


class TestApplyWhen:
    def test_variant_filter_skips_when_not_matching(self, fake_db, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        km = svc.create_key_map('k', '', 'X')
        kid = km['id']
        fam = svc.add_family(kid, 'UG')   # default family
        # Variant only fires when source.is_international == True.
        svc.add_variant(fam['id'], 'International',
                         overlay={'flag': 'yes'},
                         applies_when={'match': [{'source_column': 'is_international',
                                                  'equals': True}]})
        svc.add_variant(fam['id'], 'Base', overlay={'flag': 'base'})
        result = svc.resolve_and_expand(kid, [
            {'is_international': True},
            {'is_international': False},
        ], sf_client=MagicMock())
        # First row: both variants apply (2 rows). Second row: only Base (1 row).
        assert result['summary']['output_count'] == 3
        first = [r for r in result['output_rows'] if r['_source_row_idx'] == 0]
        second = [r for r in result['output_rows'] if r['_source_row_idx'] == 1]
        assert {r['_variant'] for r in first} == {'International', 'Base'}
        assert {r['_variant'] for r in second} == {'Base'}


class TestSaveRun:
    def test_save_run_writes_full_payload(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        run_id = svc.save_run(km['id'], 'dev', {
            'output_rows': [{'a': 1}],
            'unresolved_fks': [],
            'summary': {'source_count': 1, 'output_count': 1},
        })
        assert run_id is not None
        stored = fake_db.tables['key_map_runs'][run_id]
        assert stored['status'] == 'success'
        assert stored['output_count'] == 1

    def test_save_run_marks_partial_when_unresolved(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        run_id = svc.save_run(km['id'], 'dev', {
            'output_rows': [],
            'unresolved_fks': [{'row_idx': 0, 'value': 'X'}],
            'summary': {},
        })
        assert fake_db.tables['key_map_runs'][run_id]['status'] == 'partial'


class TestEngineErrorPaths:
    def test_resolve_missing_key_map_raises(self, fake_db):
        with pytest.raises(ValueError, match='not found'):
            svc.resolve_and_expand(999, [], sf_client=MagicMock())

    def test_resolve_no_families_raises(self, fake_db):
        km = svc.create_key_map('k', '', 'X')
        with pytest.raises(ValueError, match='no families'):
            svc.resolve_and_expand(km['id'], [{}], sf_client=MagicMock())

    def test_no_db_list_returns_empty(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        assert svc.list_key_maps() == []

    def test_no_db_create_raises(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        with pytest.raises(RuntimeError, match='database connection'):
            svc.create_key_map('n', '', 'X')
