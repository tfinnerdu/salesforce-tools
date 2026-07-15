"""Route-level tests for the meta blueprint (shared object-picker source).

`cli_metadata.list_objects` is patched so no live SF is needed; these verify the
HTTP wiring: the {success, data} envelope, that capability flags pass through,
and the standards error envelope on failure.

Real routes live under /api/v1/meta (meta_api_bp); the bare /meta prefix
(meta_bp) only survives as a 308 redirect there for pre-versioning callers.
"""
import routes.meta as route


class TestMetaObjects:
    def test_objects_envelope_and_flags(self, client, monkeypatch):
        monkeypatch.setattr(route.cli_metadata, 'list_objects', lambda org: [
            {'name': 'Account', 'label': 'Account', 'custom': False,
             'queryable': True, 'layoutable': True, 'createable': True,
             'updateable': True, 'deletable': True},
            {'name': 'ContentDocumentLink', 'label': 'Content Document Link',
             'custom': False, 'queryable': True, 'layoutable': False,
             'createable': True, 'updateable': False, 'deletable': True},
        ])
        resp = client.get('/api/v1/meta/objects')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        by_name = {o['name']: o for o in body['data']}
        # The capability flags the front-end picker filters on must survive.
        assert by_name['Account']['layoutable'] is True
        assert by_name['ContentDocumentLink']['layoutable'] is False
        assert by_name['ContentDocumentLink']['queryable'] is True

    def test_objects_uses_active_org(self, client, monkeypatch):
        seen = {}
        def _capture(org):
            seen['org'] = org
            return []
        monkeypatch.setattr(route.cli_metadata, 'list_objects', _capture)
        with client.session_transaction() as sess:
            sess['active_org'] = 'eda'
        client.get('/api/v1/meta/objects')
        assert seen['org'] == 'eda'

    def test_objects_error_envelope(self, client, monkeypatch):
        def _boom(org):
            raise RuntimeError('no creds for org')
        monkeypatch.setattr(route.cli_metadata, 'list_objects', _boom)
        resp = client.get('/api/v1/meta/objects')
        assert resp.status_code == 502
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == 'SF_DESCRIBE_FAILED'
        assert 'request_id' in body and body['request_id'] != 'unknown'


class TestMetaLegacyRedirect:
    def test_old_path_redirects_to_versioned_path(self, client):
        resp = client.get('/meta/objects', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/meta/objects')

    def test_old_path_redirect_preserves_query_string(self, client):
        resp = client.get('/meta/objects?foo=bar', follow_redirects=False)
        assert resp.status_code == 308
        assert resp.headers['Location'].endswith('/api/v1/meta/objects?foo=bar')

    def test_old_path_redirect_is_followable(self, client, monkeypatch):
        monkeypatch.setattr(route.cli_metadata, 'list_objects', lambda org: [])
        resp = client.get('/meta/objects', follow_redirects=True)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
