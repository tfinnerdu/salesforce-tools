"""Route tests for the Data Ops file-migration endpoints (plan / run).

build_plan and get_sf are patched so no live org is needed; these verify the
multipart wiring, the {success,data} envelope, the dry-run summary, and that
/run adds the commit counts.
"""
from io import BytesIO
from unittest.mock import MagicMock

import services.file_migration as fm
import sf_provider

_FAKE_PLAN = [{
    'doc_id': '069A',
    'meta': {'id': '068A', 'title': 'photo', 'size': 2048},
    'target_parents': ['a1NEW'],
    'unresolved_parents': [],
    'oversize': False,
}]


def _multipart(extra=None):
    data = {'source': 'eda', 'target': 'prod',
            'map_old_col': 'old_id', 'map_new_col': 'new_id',
            'crosswalk_csv': (BytesIO(b'old_id,new_id\na1OLD,a1NEW\n'), 'map.csv')}
    if extra:
        data.update(extra)
    return data


def _patch(monkeypatch, counts=None):
    monkeypatch.setattr(sf_provider, 'get_sf', lambda org: MagicMock())
    monkeypatch.setattr(fm, 'build_plan', lambda s, t, c: (
        _FAKE_PLAN, {}, {},
        {'parents_in_scope': 1, 'links_found': 1, 'files_found': 1}))
    if counts is not None:
        monkeypatch.setattr(
            fm, 'execute',
            lambda s, t, p, source_mode='files', dest_mode='files',
            share_type='V', visibility='AllUsers': counts)


def test_plan_dry_run_envelope(client, monkeypatch):
    _patch(monkeypatch)
    resp = client.post('/data-ops/file-migration/plan', data=_multipart(),
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    data = body['data']
    assert data['committed'] is False
    assert data['summary']['migrate'] == 1
    assert data['summary']['parents_in_scope'] == 1   # scope diagnostics surfaced
    assert data['summary']['files_found'] == 1
    assert data['rows'][0]['action'] == 'MIGRATE'
    assert 'counts' not in data           # dry-run never executes


def test_plan_requires_file(client, monkeypatch):
    _patch(monkeypatch)
    resp = client.post('/data-ops/file-migration/plan',
                       data={'source': 'eda', 'target': 'prod'},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_run_commits_and_returns_counts(client, monkeypatch):
    counts = {'created': 1, 'reused': 0, 'linked': 1, 'skipped': 0}
    _patch(monkeypatch, counts=counts)
    resp = client.post('/data-ops/file-migration/run', data=_multipart(),
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['committed'] is True
    assert data['counts'] == counts


def test_run_threads_source_and_dest_modes(client, monkeypatch):
    # The read side (mode) and write side (dest) plus link options reach execute().
    captured = {}
    monkeypatch.setattr(sf_provider, 'get_sf', lambda org: MagicMock())
    monkeypatch.setattr(fm, 'build_plan', lambda s, t, c: (
        _FAKE_PLAN, {}, {},
        {'parents_in_scope': 1, 'links_found': 1, 'files_found': 1}))

    def fake_exec(s, t, p, source_mode='files', dest_mode='files',
                  share_type='V', visibility='AllUsers'):
        captured.update(source_mode=source_mode, dest_mode=dest_mode,
                        share_type=share_type, visibility=visibility)
        return {'created': 1, 'reused': 0, 'linked': 1, 'skipped': 0}

    monkeypatch.setattr(fm, 'execute', fake_exec)
    resp = client.post('/data-ops/file-migration/run',
                       data=_multipart({'mode': 'attachments', 'dest': 'files',
                                        'share_type': 'C', 'visibility': 'InternalUsers'}),
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert captured == {'source_mode': 'attachments', 'dest_mode': 'files',
                        'share_type': 'C', 'visibility': 'InternalUsers'}


def test_ext_id_remap_requires_parent_and_extid(client, monkeypatch):
    _patch(monkeypatch)
    resp = client.post('/data-ops/file-migration/plan',
                       data={'source': 'eda', 'target': 'prod',
                             'remap_method': 'ext_id', 'ext_id': 'SIS_ID__c'},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_identity_remap_plan_ok(client, monkeypatch):
    # In-place conversion: no crosswalk, scope by filter on a parent object.
    _patch(monkeypatch)
    resp = client.post('/data-ops/file-migration/plan',
                       data={'source': 'prod', 'target': 'prod',
                             'remap_method': 'identity', 'parent': 'Accommodation__c',
                             'by': 'filter', 'where': 'Id != null'},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['data']['summary']['migrate'] == 1


def test_identity_filter_requires_parent(client, monkeypatch):
    _patch(monkeypatch)
    resp = client.post('/data-ops/file-migration/plan',
                       data={'source': 'prod', 'target': 'prod',
                             'remap_method': 'identity', 'by': 'filter'},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
