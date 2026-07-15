"""Tests for services.metadata_diff — org-to-org metadata comparison."""
from unittest.mock import MagicMock, patch

import pytest

from services import metadata_diff


# ── Salesforce doubles ────────────────────────────────────────────────────────
#
# metadata_diff fetches:
#   apex_classes / apex_triggers / validation_rules / custom_objects → Tooling
#       API via sf.restful('tooling/query/', params={'q': soql})
#   flows → Data API via sf.query_all(soql)


def _make_sf(apex_classes=(), apex_triggers=(), flows=(),
             validation_rules=(), custom_objects=()):
    """Build a Salesforce double seeded with per-metadata-type records."""
    sf = MagicMock()

    def restful(path, params=None):
        q = (params or {}).get('q', '')
        if 'FROM ApexClass' in q:
            rows = apex_classes
        elif 'FROM ApexTrigger' in q:
            rows = apex_triggers
        elif 'FROM ValidationRule' in q:
            rows = validation_rules
        elif 'FROM EntityDefinition' in q:
            rows = custom_objects
        else:
            rows = ()
        return {'records': list(rows), 'totalSize': len(rows), 'done': True}

    def query_all(soql):
        rows = flows if 'FlowDefinitionView' in soql else ()
        return {'records': list(rows), 'totalSize': len(rows), 'done': True}

    sf.restful.side_effect = restful
    sf.query_all.side_effect = query_all
    return sf


# dev sandbox: full baseline.
_DEV_SF = _make_sf(
    apex_classes=[
        {'Name': 'MigrationBatchScheduler', 'ApiVersion': '59.0',
         'LengthWithoutComments': 1200, 'Status': 'Active'},
        {'Name': 'StudentSyncService', 'ApiVersion': '59.0',
         'LengthWithoutComments': 3400, 'Status': 'Active'},
    ],
    apex_triggers=[
        {'Name': 'AccountTrigger', 'Status': 'Active', 'ApiVersion': '59.0',
         'LengthWithoutComments': 800,
         'EntityDefinition': {'QualifiedApiName': 'Account'}},
    ],
    flows=[
        {'ApiName': 'Student_Onboarding', 'Label': 'Student Onboarding',
         'ProcessType': 'Flow', 'IsActive': True},
    ],
    validation_rules=[
        {'ValidationName': 'Require_SIS_ID', 'Active': True,
         'EntityDefinition': {'QualifiedApiName': 'Account'}},
    ],
    custom_objects=[
        {'QualifiedApiName': 'Migration_Log__c', 'Label': 'Migration Log',
         'InternalSharingModel': 'Private'},
    ],
)

# prod: lags dev — missing MigrationBatchScheduler, StudentSyncService modified,
# plus a legacy class only present in prod.
_PROD_SF = _make_sf(
    apex_classes=[
        {'Name': 'StudentSyncService', 'ApiVersion': '57.0',
         'LengthWithoutComments': 3100, 'Status': 'Active'},
        {'Name': 'LegacyEDAContactSync', 'ApiVersion': '57.0',
         'LengthWithoutComments': 2000, 'Status': 'Active'},
    ],
    apex_triggers=[
        {'Name': 'AccountTrigger', 'Status': 'Active', 'ApiVersion': '57.0',
         'LengthWithoutComments': 800,
         'EntityDefinition': {'QualifiedApiName': 'Account'}},
    ],
    flows=[
        {'ApiName': 'Student_Onboarding', 'Label': 'Student Onboarding',
         'ProcessType': 'Flow', 'IsActive': True},
    ],
    validation_rules=[
        {'ValidationName': 'Require_SIS_ID', 'Active': True,
         'EntityDefinition': {'QualifiedApiName': 'Account'}},
    ],
    custom_objects=[
        {'QualifiedApiName': 'Migration_Log__c', 'Label': 'Migration Log',
         'InternalSharingModel': 'Private'},
    ],
)


def _patched_get_sf(org):
    return _DEV_SF if org == 'dev' else _PROD_SF


# ── diff_components (pure logic) ──────────────────────────────────────────────

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


# ── run_metadata_diff ─────────────────────────────────────────────────────────

def test_run_metadata_diff_dev_vs_prod_finds_differences():
    with patch('sf_provider._configured', return_value=True), \
         patch('services.metadata_diff.get_sf', side_effect=_patched_get_sf):
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
    with patch('sf_provider._configured', return_value=True), \
         patch('services.metadata_diff.get_sf', return_value=_DEV_SF):
        result = metadata_diff.run_metadata_diff('dev', 'dev')
    assert result['total_differences'] == 0


def test_run_metadata_diff_respects_type_filter():
    with patch('sf_provider._configured', return_value=True), \
         patch('services.metadata_diff.get_sf', side_effect=_patched_get_sf):
        result = metadata_diff.run_metadata_diff('dev', 'prod', types=['flows'])
    assert len(result['types']) == 1
    assert result['types'][0]['type'] == 'flows'


def test_run_metadata_diff_ignores_unknown_types_and_falls_back_to_all():
    with patch('sf_provider._configured', return_value=True), \
         patch('services.metadata_diff.get_sf', side_effect=_patched_get_sf):
        result = metadata_diff.run_metadata_diff('dev', 'prod', types=['bogus'])
    assert len(result['types']) == len(metadata_diff.METADATA_TYPES)


def test_run_metadata_diff_rejects_unconfigured_org():
    """run_metadata_diff must raise when an org has no credentials configured."""
    with patch('sf_provider._configured', side_effect=lambda org: org == 'sandbox'):
        with pytest.raises(ValueError, match='no Salesforce credentials'):
            metadata_diff.run_metadata_diff('sandbox', 'prod')


# ── available_orgs — only configured orgs are offered ─────────────────────────

def test_available_orgs_filters_to_configured():
    import sf_provider
    with patch('sf_provider._configured', side_effect=lambda org: org == 'sandbox'):
        assert sf_provider.available_orgs() == ['sandbox']


def test_available_orgs_empty_when_none_configured():
    import sf_provider
    with patch('sf_provider._configured', return_value=False):
        assert sf_provider.available_orgs() == []


# ── Routes ────────────────────────────────────────────────────────────────────

def test_metadata_diff_page_renders(client):
    resp = client.get('/schema/metadata-diff')
    assert resp.status_code == 200
    assert b'Org Metadata Diff' in resp.data


def test_metadata_diff_run_route(client):
    with patch('sf_provider._configured', return_value=True), \
         patch('services.metadata_diff.get_sf', side_effect=_patched_get_sf):
        resp = client.post('/api/v1/schema/metadata-diff/run', json={'compare_org': 'prod'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['total_differences'] > 0


def test_metadata_diff_run_error_returns_500(client, monkeypatch):
    import services.metadata_diff as md
    monkeypatch.setattr(md, 'run_metadata_diff',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/api/v1/schema/metadata-diff/run', json={})
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
