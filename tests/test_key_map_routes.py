"""Route-level tests for the key_map blueprint.

The service layer is unit-tested in test_key_map.py; these tests verify the
HTTP wiring — status codes, the {success, data} envelope, and that preview/
export reach the engine — by patching routes.key_map.svc so they don't need
a database.

Real JSON/action routes live under /api/v1/key-maps (key_map_api_bp); the
bare /key-maps prefix (key_map_bp) still serves the HTML admin pages and
only survives as a 308 redirect for the JSON paths for pre-versioning
callers.
"""
import pytest

import routes.key_map as route


# ── Page routes render ───────────────────────────────────────────────────────

class TestPages:
    @pytest.mark.parametrize('path', [
        '/key-maps', '/key-maps/', '/key-maps/new', '/key-maps/5', '/key-maps/5/run',
    ])
    def test_pages_render_200(self, client, path):
        assert client.get(path).status_code == 200


# ── CRUD envelopes ───────────────────────────────────────────────────────────

class TestCrudRoutes:
    def test_list(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'list_key_maps',
                            lambda: [{'id': 1, 'name': 'PTAT'}])
        resp = client.get('/api/v1/key-maps/list')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data'][0]['name'] == 'PTAT'

    def test_get_404_when_missing(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'get_key_map', lambda *a, **k: None)
        resp = client.get('/api/v1/key-maps/get/99')
        assert resp.status_code == 404
        assert resp.get_json()['success'] is False

    def test_create_201(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'create_key_map',
                            lambda **k: {'id': 1, **k})
        resp = client.post('/api/v1/key-maps/create',
                           json={'name': 'PTAT', 'target_sobject': 'ProgramTermApplnTimeline'})
        assert resp.status_code == 201
        assert resp.get_json()['data']['name'] == 'PTAT'

    def test_create_400_on_value_error(self, client, monkeypatch):
        def _raise(**k):
            raise ValueError('name is required')
        monkeypatch.setattr(route.svc, 'create_key_map', _raise)
        resp = client.post('/api/v1/key-maps/create', json={'name': ''})
        assert resp.status_code == 400
        assert 'name is required' in resp.get_json()['error']

    def test_delete(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'delete_key_map', lambda i: True)
        resp = client.delete('/api/v1/key-maps/3')
        assert resp.status_code == 200
        assert resp.get_json()['data']['deleted'] == 3

    def test_delete_404(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'delete_key_map', lambda i: False)
        assert client.delete('/api/v1/key-maps/3').status_code == 404


class TestChildRoutes:
    def test_add_fk_lookup(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'add_fk_lookup', lambda *a, **k: {'id': 1, **k})
        resp = client.post('/api/v1/key-maps/1/fk-lookups', json={
            'source_column': 'TERMS_ID', 'target_field': 'AcademicTermId',
            'lookup_sobject': 'AcademicTerm'})
        assert resp.status_code == 201
        assert resp.get_json()['data']['lookup_sobject'] == 'AcademicTerm'

    def test_add_family(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'add_family', lambda *a, **k: {'id': 2, **k})
        resp = client.post('/api/v1/key-maps/1/families',
                           json={'name': 'UG', 'routing': {'match': []}})
        assert resp.status_code == 201

    def test_add_variant(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'add_variant', lambda *a, **k: {'id': 3, **k})
        resp = client.post('/api/v1/key-maps/families/2/variants',
                           json={'name': 'Base', 'overlay': {'X': 'Y'}})
        assert resp.status_code == 201

    def test_add_variant_400_on_bad_overlay(self, client, monkeypatch):
        def _raise(*a, **k):
            raise ValueError('overlay must be an object')
        monkeypatch.setattr(route.svc, 'add_variant', _raise)
        resp = client.post('/api/v1/key-maps/families/2/variants',
                           json={'name': 'Base', 'overlay': {}})
        assert resp.status_code == 400

    def test_add_variant_forwards_applies_when(self, client, monkeypatch):
        captured = {}
        def _capture(family_id, name, overlay, applies_when, position):
            captured.update(family_id=family_id, name=name, overlay=overlay,
                            applies_when=applies_when)
            return {'id': 9, 'name': name}
        monkeypatch.setattr(route.svc, 'add_variant', _capture)
        resp = client.post('/api/v1/key-maps/families/2/variants', json={
            'name': 'International',
            'overlay': {'Pre_decision_Requirements_Action_Plan__c': 'PRE_INTL'},
            'applies_when': {'match': [{'source_column': 'is_intl', 'equals': 'Y'}]},
        })
        assert resp.status_code == 201
        assert captured['family_id'] == 2
        assert captured['overlay']['Pre_decision_Requirements_Action_Plan__c'] == 'PRE_INTL'
        assert captured['applies_when']['match'][0]['source_column'] == 'is_intl'


# ── Preview + export ─────────────────────────────────────────────────────────

class TestPreviewExport:
    _RESULT = {
        'output_rows': [{'AcademicTermId': 'T1', '_family': 'UG', '_variant': 'Base'}],
        'unresolved_fks': [],
        'summary': {'source_count': 1, 'output_count': 1, 'unresolved_count': 0,
                    'skipped_no_family': 0},
    }

    def test_preview_returns_summary_and_sample(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'resolve_and_expand', lambda *a, **k: self._RESULT)
        monkeypatch.setattr(route.svc, 'save_run', lambda *a, **k: 7)
        resp = client.post('/api/v1/key-maps/1/preview', json={
            'source': {'mode': 'inline', 'rows': [{'TERMS_ID': '23/AUTM'}]}})
        assert resp.status_code == 200
        d = resp.get_json()['data']
        assert d['run_id'] == 7
        assert d['summary']['output_count'] == 1
        assert d['sample_rows'][0]['_variant'] == 'Base'

    def test_preview_400_on_bad_source(self, client):
        # No service patch needed — ingest.load_source_rows rejects this first.
        resp = client.post('/api/v1/key-maps/1/preview', json={'source': {'mode': 'telepathy'}})
        assert resp.status_code == 400
        assert 'Unknown source mode' in resp.get_json()['error']

    def test_export_streams_csv(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'resolve_and_expand', lambda *a, **k: self._RESULT)
        monkeypatch.setattr(route.svc, 'save_run', lambda *a, **k: 7)
        monkeypatch.setattr(route.svc, 'get_key_map', lambda *a, **k: {'name': 'PTAT'})
        resp = client.post('/api/v1/key-maps/1/export', json={
            'source': {'mode': 'inline', 'rows': [{'TERMS_ID': '23/AUTM'}]}})
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'
        body = resp.get_data(as_text=True)
        assert 'AcademicTermId' in body
        assert '_variant' in body          # meta columns kept for traceability
        assert 'T1' in body


def test_rows_to_csv_empty_returns_empty():
    assert route._rows_to_csv([]) == ''


def test_rows_to_csv_orders_meta_columns_last():
    csv_text = route._rows_to_csv([{'A': 1, '_family': 'UG', '_variant': 'Base'}])
    header = csv_text.splitlines()[0]
    assert header.startswith('A')
    assert header.index('A') < header.index('_family')


class TestKeyMapLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/key-maps/list', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/key-maps/list')

    def test_old_path_redirect_is_followable(self, client, monkeypatch):
        monkeypatch.setattr(route.svc, 'list_key_maps', lambda: [])
        resp = client.get('/key-maps/list', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
