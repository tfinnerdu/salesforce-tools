#!/usr/bin/env python3
"""Org-to-org Salesforce file (ContentVersion) migrator — EDA → Ed Cloud.

Streams files from a source org to a target org **without staging them locally**
and relinks each file to the migrated parent record by resolving an external-ID
field (e.g. ``SIS_ID__c``) — because parent records get new Ids in the target.

- **Dry-run by default.** It reads, resolves parents, and reports, but writes
  NOTHING until you pass ``--commit``.
- **Idempotent.** Each created ContentVersion is stamped with the source
  ContentVersion Id in ``ExternalDocumentInfo1``, so re-runs skip files that
  were already migrated.
- **Two scope modes:** ``--by filter`` (a SOQL WHERE on the parent object) or
  ``--by list`` (a file of parent record Ids or external-Id values, one per
  line).

Reuses the app's ``sf_provider.get_sf`` (so it authenticates with the same
configured org credentials) and ``utils.soql.escape_soql``. This is the
standalone engine behind the future File Migration tab (Phase 2).

Examples
--------
    # Dry run — all files on Person Accounts, matched by SIS_ID__c
    python scripts/migrate_files.py --source eda --target prod \
        --parent Account --ext-id SIS_ID__c --by filter --where "IsPersonAccount = true"

    # Explicit list of parents by external Id (one value per line)
    python scripts/migrate_files.py --source eda --target prod \
        --parent Case --ext-id Legacy_Case_Id__c --by list --ids-file cases.txt

    # Same command with --commit actually writes to the target org
    python scripts/migrate_files.py ... --commit
"""
import argparse
import base64
import csv
import logging
import os
import sys

# Allow running from the repo root: make the app package importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import requests  # noqa: E402

from sf_provider import get_sf  # noqa: E402
from utils.soql import escape_soql, is_sf_id  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('migrate_files')

# Single-call base64 inserts are bounded by the request/heap size; larger files
# need a multipart upload (not implemented here). Flag them instead of failing.
DEFAULT_MAX_MB = 35
_CHUNK = 200


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

def chunked(seq, n=_CHUNK):
    """Yield successive n-sized chunks of a list (for IN() batching)."""
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def soql_in_list(values):
    """Render a SOQL IN() body from values, each escaped and quoted."""
    return ', '.join("'" + escape_soql(v) + "'" for v in values)


def load_id_map(path, old_col='old_id', new_col='new_id'):
    """Load an old-parent-Id → new-parent-Id crosswalk from a CSV.

    Reads the columns named ``old_col`` / ``new_col`` if present, else falls back
    to the first two columns — so you can point ``--id-map`` straight at an
    existing migration spreadsheet (e.g. ``--map-old-col Accommodation__c
    --map-new-col NEW_Accommodation__c``). Rows with a blank old or new value are
    skipped; the last value wins on duplicate old Ids.
    """
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return {}
    header = rows[0]
    try:
        oi, ni = header.index(old_col), header.index(new_col)
        data_rows = rows[1:]
    except ValueError:
        # Named columns not found — treat as a headerless two-column file.
        oi, ni = 0, 1
        data_rows = rows if header[:1] and header[0] != old_col else rows[1:]
    id_map = {}
    for r in data_rows:
        if len(r) <= max(oi, ni):
            continue
        old, new = r[oi].strip(), r[ni].strip()
        if old and new:
            id_map[old] = new
    return id_map


def compose_parent_map(src_id_to_ext, ext_to_target_id):
    """Compose source-parent-Id → target-parent-Id via the shared external Id.

    Pure: given ``{source_parent_id: ext_value}`` and ``{ext_value: target_id}``,
    return ``(resolved, unresolved)`` where ``resolved`` maps source parent Id →
    target Id and ``unresolved`` maps source parent Id → reason. Kept separate
    from the SF I/O so the remap logic is testable without a live org.
    """
    resolved, unresolved = {}, {}
    for src_id, ext in src_id_to_ext.items():
        if not ext:
            unresolved[src_id] = 'source record has no external-Id value'
            continue
        target_id = ext_to_target_id.get(ext)
        if not target_id:
            unresolved[src_id] = f'no target record with external Id {ext!r}'
            continue
        resolved[src_id] = target_id
    return resolved, unresolved


# ── Salesforce reads ──────────────────────────────────────────────────────────

def _query_all(sf, soql):
    return sf.query_all(soql).get('records', [])


def scope_parent_ids(sf, cfg):
    """Return the set of source parent record Ids in scope (filter or list mode)."""
    if cfg.by == 'filter':
        where = cfg.where or 'Id != null'
        rows = _query_all(sf, f"SELECT Id FROM {cfg.parent} WHERE {where}")
        return [r['Id'] for r in rows if r.get('Id')]

    # list mode: file of Ids or external-Id values, one per line
    with open(cfg.ids_file, encoding='utf-8') as fh:
        raw = [ln.strip() for ln in fh if ln.strip()]
    ids, ext_values = [], []
    for v in raw:
        (ids if is_sf_id(v) else ext_values).append(v)
    if ext_values:
        for batch in chunked(ext_values):
            rows = _query_all(
                sf, f"SELECT Id FROM {cfg.parent} "
                    f"WHERE {cfg.ext_id} IN ({soql_in_list(batch)})")
            ids.extend(r['Id'] for r in rows if r.get('Id'))
    return list(dict.fromkeys(ids))  # de-dupe, preserve order


def gather_files(sf, parent_ids):
    """Return (links, files) for the given source parents.

    links : list of {'doc': ContentDocumentId, 'parent': LinkedEntityId}
    files : {ContentDocumentId: {id,title,path,ext,size}} for the latest version
    """
    links = []
    for batch in chunked(parent_ids):
        rows = _query_all(
            sf, "SELECT ContentDocumentId, LinkedEntityId FROM ContentDocumentLink "
                f"WHERE LinkedEntityId IN ({soql_in_list(batch)})")
        for r in rows:
            doc, parent = r.get('ContentDocumentId'), r.get('LinkedEntityId')
            if doc and parent:
                links.append({'doc': doc, 'parent': parent})

    doc_ids = list({lk['doc'] for lk in links})
    files = {}
    for batch in chunked(doc_ids):
        rows = _query_all(
            sf, "SELECT Id, Title, PathOnClient, FileExtension, ContentDocumentId, "
                "ContentSize FROM ContentVersion "
                f"WHERE ContentDocumentId IN ({soql_in_list(batch)}) AND IsLatest = true")
        for r in rows:
            doc_id = r.get('ContentDocumentId')
            if not doc_id:
                continue
            files[doc_id] = {
                'id': r['Id'],
                'title': r.get('Title') or 'file',
                'path': r.get('PathOnClient') or r.get('Title') or 'file',
                'ext': r.get('FileExtension') or '',
                'size': r.get('ContentSize') or 0,
            }
    return links, files


def resolve_parents(source_sf, target_sf, cfg, parent_ids):
    """Map each source parent Id → target Id by matching cfg.ext_id across orgs."""
    src_id_to_ext = {}
    for batch in chunked(parent_ids):
        rows = _query_all(
            source_sf, f"SELECT Id, {cfg.ext_id} FROM {cfg.parent} "
                       f"WHERE Id IN ({soql_in_list(batch)})")
        for r in rows:
            if r.get('Id'):
                src_id_to_ext[r['Id']] = r.get(cfg.ext_id)

    ext_values = [v for v in src_id_to_ext.values() if v]
    ext_to_target_id = {}
    for batch in chunked(list(dict.fromkeys(ext_values))):
        rows = _query_all(
            target_sf, f"SELECT Id, {cfg.ext_id} FROM {cfg.parent} "
                       f"WHERE {cfg.ext_id} IN ({soql_in_list(batch)})")
        for r in rows:
            if r.get(cfg.ext_id) and r.get('Id'):
                ext_to_target_id[r[cfg.ext_id]] = r['Id']

    return compose_parent_map(src_id_to_ext, ext_to_target_id)


def download_version_data(sf, cv_id):
    """Stream a file's bytes from the source org (no local staging)."""
    url = f"{sf.base_url}sobjects/ContentVersion/{cv_id}/VersionData"
    resp = requests.get(url, headers={'Authorization': f'Bearer {sf.session_id}'},
                        timeout=120)
    resp.raise_for_status()
    return resp.content


def existing_target_doc(target_sf, src_cv_id):
    """ContentDocumentId of an already-migrated file (stamped), or None."""
    rows = _query_all(
        target_sf, "SELECT ContentDocumentId FROM ContentVersion "
                   f"WHERE ExternalDocumentInfo1 = '{escape_soql(src_cv_id)}' "
                   "AND IsLatest = true")
    return rows[0]['ContentDocumentId'] if rows else None


# ── Salesforce writes (only when --commit) ────────────────────────────────────

def insert_content_version(target_sf, file_meta, data):
    """Create a ContentVersion in the target from bytes; return its ContentDocumentId."""
    res = target_sf.ContentVersion.create({
        'Title': file_meta['title'],
        'PathOnClient': file_meta['path'],
        'VersionData': base64.b64encode(data).decode('ascii'),
        'ExternalDocumentInfo1': file_meta['id'],   # idempotency stamp (source CV Id)
    })
    rows = _query_all(
        target_sf, "SELECT ContentDocumentId FROM ContentVersion "
                   f"WHERE Id = '{escape_soql(res['id'])}'")
    return rows[0]['ContentDocumentId']


def create_link(target_sf, doc_id, target_parent_id):
    """Link a document to a parent; return True if created, False if it already
    existed (a re-run over an already-linked file — not an error)."""
    try:
        target_sf.ContentDocumentLink.create({
            'ContentDocumentId': doc_id,
            'LinkedEntityId': target_parent_id,
            'ShareType': 'V',
            'Visibility': 'AllUsers',
        })
        return True
    except Exception as exc:
        msg = str(exc).upper()
        if 'DUPLICATE' in msg or 'ALREADY' in msg:
            return False
        raise


# ── Orchestration ─────────────────────────────────────────────────────────────

def build_plan(source_sf, target_sf, cfg):
    """Read + resolve everything; return (plan_rows, resolved, unresolved)."""
    if cfg.id_map:
        # Crosswalk mode: the CSV already carries old→new parent Ids, so scope
        # (its keys) and remap come straight from it — no external-Id lookups.
        resolved = load_id_map(cfg.id_map, cfg.map_old_col, cfg.map_new_col)
        unresolved = {}
        parent_ids = list(resolved.keys())
        logger.info('Scope: %d parent Id(s) from crosswalk %s.', len(parent_ids), cfg.id_map)
    else:
        # External-Id mode: resolve after we know which parents actually have files.
        resolved = None
        unresolved = {}
        parent_ids = scope_parent_ids(source_sf, cfg)
        logger.info('Scope: %d source parent record(s).', len(parent_ids))

    if not parent_ids:
        return [], {}, {}

    links, files = gather_files(source_sf, parent_ids)
    if resolved is None:
        resolved, unresolved = resolve_parents(source_sf, target_sf, cfg, parent_ids)
    logger.info('Files: %d unique across %d link(s). Parents resolved: %d, unresolved: %d.',
                len(files), len(links), len(resolved), len(unresolved))

    # One row per file (deduped by ContentDocument); each carries the resolved
    # target parents it should be linked to.
    by_doc = {}
    for lk in links:
        by_doc.setdefault(lk['doc'], []).append(lk['parent'])

    max_bytes = cfg.max_mb * 1024 * 1024
    plan = []
    for doc_id, src_parents in by_doc.items():
        meta = files.get(doc_id)
        if not meta:
            continue
        targets = [resolved[p] for p in src_parents if p in resolved]
        skipped_parents = [p for p in src_parents if p not in resolved]
        oversize = meta['size'] > max_bytes
        plan.append({
            'doc_id': doc_id,
            'meta': meta,
            'target_parents': list(dict.fromkeys(targets)),
            'unresolved_parents': skipped_parents,
            'oversize': oversize,
        })
    return plan, resolved, unresolved


def write_report(path, plan):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['source_cv_id', 'title', 'size_bytes', 'resolved_parents',
                    'unresolved_parents', 'oversize', 'action'])
        for row in plan:
            m = row['meta']
            action = ('SKIP (too large — needs multipart)' if row['oversize']
                      else 'MIGRATE' if row['target_parents']
                      else 'SKIP (no resolved parent)')
            w.writerow([m['id'], m['title'], m['size'], len(row['target_parents']),
                        len(row['unresolved_parents']), row['oversize'], action])
    logger.info('Report written: %s', path)


def execute(source_sf, target_sf, plan):
    """Perform the migration for a plan (idempotent). Returns counts.

    For each file: skip if oversize or no parent resolved; reuse the target
    ContentDocument if this source file was already migrated (stamp match);
    otherwise stream the bytes from source and insert into target. Then link the
    (new or reused) document to every resolved target parent.
    """
    created = linked = skipped = reused = 0
    for row in plan:
        meta, targets = row['meta'], row['target_parents']
        if row['oversize'] or not targets:
            skipped += 1
            continue
        doc_id = existing_target_doc(target_sf, meta['id'])
        if doc_id:
            reused += 1
        else:
            data = download_version_data(source_sf, meta['id'])
            doc_id = insert_content_version(target_sf, meta, data)
            created += 1
        for tid in targets:
            if create_link(target_sf, doc_id, tid):
                linked += 1
    return {'created': created, 'reused': reused, 'linked': linked, 'skipped': skipped}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', required=True, help='source org name (e.g. eda)')
    ap.add_argument('--target', required=True, help='target org name (e.g. prod)')
    ap.add_argument('--parent', default='', help='parent SObject (e.g. Account, Case) — '
                    'required unless --id-map is used')
    ap.add_argument('--ext-id', default='', dest='ext_id',
                    help='external-Id field on the parent to remap old→new (e.g. SIS_ID__c) — '
                    'required unless --id-map is used')
    ap.add_argument('--by', choices=['filter', 'list'], default='filter',
                    help='scope mode (external-Id path): SOQL filter, or a file of Ids/ext-Ids')
    ap.add_argument('--where', default='', help="SOQL WHERE for --by filter")
    ap.add_argument('--ids-file', default='', help='file of parent Ids/ext-Id values for --by list')
    ap.add_argument('--id-map', default='', help='crosswalk CSV of old→new parent Ids; when set, '
                    'it drives both scope and remap (no external-Id lookups). Point it straight '
                    'at your migration spreadsheet.')
    ap.add_argument('--map-old-col', default='old_id', help='crosswalk column with the source Id')
    ap.add_argument('--map-new-col', default='new_id', help='crosswalk column with the target Id')
    ap.add_argument('--max-mb', type=int, default=DEFAULT_MAX_MB,
                    help=f'flag files larger than this many MB (default {DEFAULT_MAX_MB})')
    ap.add_argument('--report', default='file_migration_report.csv', help='CSV report path')
    ap.add_argument('--commit', action='store_true',
                    help='actually write to the target org (default is dry-run)')
    cfg = ap.parse_args(argv)

    if cfg.id_map:
        if not os.path.exists(cfg.id_map):
            ap.error(f'--id-map file not found: {cfg.id_map}')
    else:
        # External-Id path needs the parent object + its external-Id field.
        if not cfg.parent or not cfg.ext_id:
            ap.error('--parent and --ext-id are required unless --id-map is used')
        if cfg.by == 'list' and not cfg.ids_file:
            ap.error('--by list requires --ids-file')

    source_sf = get_sf(cfg.source)
    target_sf = get_sf(cfg.target)

    remap = (f'crosswalk {cfg.id_map}' if cfg.id_map
             else f'parent {cfg.parent} by ext-Id {cfg.ext_id}')
    logger.info('Planning migration: %s → %s  (%s)', cfg.source, cfg.target, remap)
    plan, resolved, unresolved = build_plan(source_sf, target_sf, cfg)
    write_report(cfg.report, plan)

    migrate = [r for r in plan if r['target_parents'] and not r['oversize']]
    total_mb = sum(r['meta']['size'] for r in migrate) / 1024 / 1024
    oversize = [r for r in plan if r['oversize']]
    no_parent = [r for r in plan if not r['target_parents'] and not r['oversize']]
    logger.info('\n=== PLAN SUMMARY ===')
    logger.info('  migrate      : %d file(s), %.1f MB', len(migrate), total_mb)
    logger.info('  skip (no parent resolved): %d', len(no_parent))
    logger.info('  skip (too large > %d MB) : %d', cfg.max_mb, len(oversize))
    logger.info('  unresolved parents       : %d', len(unresolved))

    if not cfg.commit:
        logger.info('\nDRY RUN — nothing was written. Re-run with --commit to migrate.')
        return 0

    logger.info('\nCOMMIT — writing to %s …', cfg.target)
    counts = execute(source_sf, target_sf, plan)
    logger.info('Done. created=%(created)d reused=%(reused)d linked=%(linked)d skipped=%(skipped)d',
                counts)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
