"""Tests for services.metadata_diff — org-to-org metadata comparison."""
from services import metadata_diff


# ── diff_components ───────────────────────────────────────────────────────────

def test_diff_components_classifies_left_right_and_modified():
    left = {
        'A': {'fingerprint': 'x', 'detail': 'a-left'},
        'B': {'fingerprint': 'x', 'detail': 'b-left'},
        'C': {'fingerprint': 'old', 'detail': 'c-left'},
    }
    right = {
        'B': {'fingerprint': 'x', 'detail': 'b-right'},
        'C': {'fingerprint': 'new', 'detail': 'c-right'},
        'D': {'fingerprint': 'x', 'detail': 'd-right'},
    }
    diff = metadata_diff.diff_components(left, right)
    assert [i['name'] for i in diff['left_only']] == ['A']
    assert [i['name'] for i in diff['right_only']] == ['D']
    assert [m['name'] for m in diff['modified']] == ['C']
    assert diff['modified'][0]['left_detail'] == 'c-left'
    assert diff['modified'][0]['right_detail'] == 'c-right'
    assert diff['identical'] == 1          # B
    assert diff['difference_count'] == 3   # A + D + C


def test_diff_components_identical_maps_have_no_differences():
    same = {'A': {'fingerprint': 'x', 'detail': 'a'}}
    diff = metadata_diff.diff_components(same, dict(same))
    assert diff['difference_count'] == 0
    assert diff['identical'] == 1


# ── _mock_components — org-aware seed ─────────────────────────────────────────

def test_mock_components_dev_returns_full_baseline():
    dev = metadata_diff._mock_components('apex_classes', 'dev')
    assert 'MigrationBatchScheduler' in dev
    assert 'StudentSyncService' in dev


def test_mock_components_prod_lags_the_dev_sandbox():
    """The 'prod' variant drops new components, modifies one, adds a legacy one."""
    prod = metadata_diff._mock_components('apex_classes', 'prod')
    assert 'MigrationBatchScheduler' not in prod          # not yet deployed
    assert 'LegacyEDAContactSync' in prod                 # legacy, only in prod
    assert prod['StudentSyncService']['fingerprint'] != \
        metadata_diff._mock_components('apex_classes', 'dev')['StudentSyncService']['fingerprint']


# ── run_metadata_diff — mock mode ─────────────────────────────────────────────

def test_run_metadata_diff_dev_vs_prod_finds_differences():
    result = metadata_diff.run_metadata_diff('dev', 'prod')
    assert result['left_org'] == 'dev'
    assert result['right_org'] == 'prod'
    assert result['total_differences'] > 0
    assert len(result['types']) == len(metadata_diff.METADATA_TYPES)
    apex = next(t for t in result['types'] if t['type'] == 'apex_classes')
    assert any(i['name'] == 'MigrationBatchScheduler' for i in apex['left_only'])
    assert any(i['name'] == 'LegacyEDAContactSync' for i in apex['right_only'])
    assert any(m['name'] == 'StudentSyncService' for m in apex['modified'])


def test_run_metadata_diff_same_org_has_no_differences():
    result = metadata_diff.run_metadata_diff('dev', 'dev')
    assert result['total_differences'] == 0


def test_run_metadata_diff_respects_type_filter():
    result = metadata_diff.run_metadata_diff('dev', 'prod', types=['flows'])
    assert len(result['types']) == 1
    assert result['types'][0]['type'] == 'flows'


def test_run_metadata_diff_ignores_unknown_types_and_falls_back_to_all():
    result = metadata_diff.run_metadata_diff('dev', 'prod', types=['bogus'])
    assert len(result['types']) == len(metadata_diff.METADATA_TYPES)


# ── Routes ────────────────────────────────────────────────────────────────────

def test_metadata_diff_page_renders(client):
    resp = client.get('/schema/metadata-diff')
    assert resp.status_code == 200
    assert b'Org Metadata Diff' in resp.data


def test_metadata_diff_run_route(client):
    resp = client.post('/schema/metadata-diff/run', json={'compare_org': 'prod'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['total_differences'] > 0


def test_metadata_diff_run_error_returns_500(client, monkeypatch):
    import services.metadata_diff as md
    monkeypatch.setattr(md, 'run_metadata_diff',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/schema/metadata-diff/run', json={})
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False


# ── _tooling_query_all — nextRecordsUrl pagination ────────────────────────────

class _PagingSF:
    """Tooling API stub that returns three pages via nextRecordsUrl."""
    def __init__(self):
        self.paths = []

    def restful(self, path, params=None):
        self.paths.append(path)
        if path == 'tooling/query/':
            return {'records': [{'Name': 'A'}],
                    'nextRecordsUrl': '/services/data/v59.0/tooling/query/01g000-2000'}
        if path == 'tooling/query/01g000-2000':
            return {'records': [{'Name': 'B'}],
                    'nextRecordsUrl': '/services/data/v59.0/tooling/query/01g000-4000'}
        if path == 'tooling/query/01g000-4000':
            return {'records': [{'Name': 'C'}]}   # no nextRecordsUrl — done
        raise AssertionError(f'unexpected path: {path}')


def test_tooling_query_all_follows_next_records_url():
    sf = _PagingSF()
    records = metadata_diff._tooling_query_all(sf, 'SELECT Name FROM ApexClass')
    assert [r['Name'] for r in records] == ['A', 'B', 'C']
    # nextRecordsUrl must be relativized to a path restful() accepts —
    # stripped of the /services/data/vXX.X/ prefix.
    assert sf.paths == ['tooling/query/',
                        'tooling/query/01g000-2000',
                        'tooling/query/01g000-4000']


def test_tooling_query_all_single_page_no_pagination():
    class _OneSF:
        def restful(self, path, params=None):
            return {'records': [{'Name': 'X'}], 'done': True}
    records = metadata_diff._tooling_query_all(_OneSF(), 'SELECT Name FROM ApexClass')
    assert [r['Name'] for r in records] == ['X']


def test_tooling_query_all_empty_result():
    class _EmptySF:
        def restful(self, path, params=None):
            return {'records': []}
    assert metadata_diff._tooling_query_all(_EmptySF(), 'SELECT Name FROM ApexClass') == []
