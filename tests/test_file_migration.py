"""Tests for services.file_migration (the shared engine).

Pure helpers are covered in test_migrate_files.py (re-exported). Here we pin the
orchestration: crosswalk build_plan, summarize/report_rows, and execute counts,
with unittest.mock doubles for the two orgs.
"""
from unittest.mock import MagicMock, patch

from services import file_migration as fm
from services.file_migration import MigrationConfig


def _source_sf(cdl, cv):
    """SF double whose query_all answers the CDL then CV queries by SOQL text."""
    sf = MagicMock()

    def q(soql):
        if 'ContentDocumentLink' in soql:
            return {'records': cdl}
        if 'ContentVersion' in soql and 'ContentDocumentId IN' in soql:
            return {'records': cv}
        return {'records': []}

    sf.query_all.side_effect = q
    return sf


# ── build_plan (crosswalk mode) ───────────────────────────────────────────────

def test_build_plan_crosswalk_maps_file_to_new_parent(tmp_path):
    csv = tmp_path / 'map.csv'
    csv.write_text('old_id,new_id\na1OLD,a1NEW\n')
    src = _source_sf(
        cdl=[{'ContentDocumentId': '069A', 'LinkedEntityId': 'a1OLD'}],
        cv=[{'Id': '068A', 'Title': 'photo', 'PathOnClient': 'photo.jpg',
             'FileExtension': 'jpg', 'ContentDocumentId': '069A', 'ContentSize': 1000}],
    )
    cfg = MigrationConfig(id_map=str(csv))
    plan, resolved, unresolved = fm.build_plan(src, MagicMock(), cfg)
    assert resolved == {'a1OLD': 'a1NEW'}
    assert len(plan) == 1
    assert plan[0]['target_parents'] == ['a1NEW']
    assert plan[0]['oversize'] is False


def test_build_plan_crosswalk_flags_oversize(tmp_path):
    csv = tmp_path / 'map.csv'
    csv.write_text('old_id,new_id\na1OLD,a1NEW\n')
    src = _source_sf(
        cdl=[{'ContentDocumentId': '069A', 'LinkedEntityId': 'a1OLD'}],
        cv=[{'Id': '068A', 'Title': 'big', 'ContentDocumentId': '069A',
             'ContentSize': 50 * 1024 * 1024}],   # 50 MB > 35 MB cap
    )
    plan, _, _ = fm.build_plan(src, MagicMock(), MigrationConfig(id_map=str(csv), max_mb=35))
    assert plan[0]['oversize'] is True


def test_build_plan_file_with_unmapped_parent_has_no_target(tmp_path):
    csv = tmp_path / 'map.csv'
    csv.write_text('old_id,new_id\na1OLD,a1NEW\n')
    # File links to a parent that's NOT in the crosswalk → no resolved target.
    src = _source_sf(
        cdl=[{'ContentDocumentId': '069A', 'LinkedEntityId': 'a1OLD'},
             {'ContentDocumentId': '069B', 'LinkedEntityId': 'zzUNMAPPED'}],
        cv=[{'Id': '068B', 'Title': 'orphan', 'ContentDocumentId': '069B', 'ContentSize': 1}],
    )
    plan, _, _ = fm.build_plan(src, MagicMock(), MigrationConfig(id_map=str(csv)))
    row = next(r for r in plan if r['doc_id'] == '069B')
    assert row['target_parents'] == []
    assert 'zzUNMAPPED' in row['unresolved_parents']


# ── summarize / report_rows ───────────────────────────────────────────────────

def _plan_row(size=10, targets=('n',), oversize=False):
    return {'doc_id': 'd',
            'meta': {'id': 's', 'title': 't', 'path': 't.jpg', 'size': size},
            'target_parents': list(targets), 'unresolved_parents': [], 'oversize': oversize}


def test_summarize_counts():
    plan = [_plan_row(size=1024 * 1024), _plan_row(targets=()),
            _plan_row(oversize=True)]
    s = fm.summarize(plan, unresolved={'x': 'reason'}, max_mb=35)
    assert s['migrate'] == 1
    assert s['migrate_mb'] == 1.0
    assert s['no_parent'] == 1
    assert s['oversize'] == 1
    assert s['unresolved_parents'] == 1


def test_report_rows_actions():
    rows = fm.report_rows([_plan_row(), _plan_row(targets=()), _plan_row(oversize=True)])
    actions = [r['action'] for r in rows]
    assert actions[0] == 'MIGRATE'
    assert 'no resolved parent' in actions[1]
    assert 'too large' in actions[2]


# ── execute ───────────────────────────────────────────────────────────────────

def test_execute_creates_and_links():
    plan = [_plan_row(size=1000, targets=('a1NEW',))]
    plan[0]['meta']['id'] = '068A'
    target = MagicMock()
    # existing_target_doc → none; then ContentDocumentId-by-Id lookup after insert.
    target.query_all.side_effect = [
        {'records': []},                                  # not already migrated
        {'records': [{'ContentDocumentId': '069NEW'}]},   # doc id of the new CV
    ]
    target.ContentVersion.create.return_value = {'id': '068NEW'}
    target.ContentDocumentLink.create.return_value = {'id': 'cdl1'}

    fake_resp = MagicMock(content=b'bytes')
    fake_resp.raise_for_status.return_value = None
    with patch('services.file_migration.requests.get', return_value=fake_resp):
        counts = fm.execute(MagicMock(), target, plan)

    assert counts == {'created': 1, 'reused': 0, 'linked': 1, 'skipped': 0}
    target.ContentVersion.create.assert_called_once()
    target.ContentDocumentLink.create.assert_called_once()


def test_execute_skips_oversize_and_no_parent():
    plan = [_plan_row(oversize=True), _plan_row(targets=())]
    counts = fm.execute(MagicMock(), MagicMock(), plan)
    assert counts['skipped'] == 2
    assert counts['created'] == 0
