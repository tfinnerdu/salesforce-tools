"""Org-to-org Salesforce file (ContentVersion) migration engine.

Shared logic behind both the CLI (``scripts/migrate_files.py``) and the Data Ops
"File migration" card. Streams files from a source org to a target org **without
staging them locally** and relinks each file to the migrated parent record —
either from a direct old→new **crosswalk** CSV or by resolving an **external-Id**
field (e.g. ``SIS_ID__c``) across the two orgs.

Read-side helpers are pure or thin over ``simple_salesforce``; the write helpers
run only from ``execute()``. ``build_plan()`` never writes — it's the dry-run.
Idempotent: created ContentVersions are stamped with the source ContentVersion
Id in ``ExternalDocumentInfo1``, so re-runs reuse instead of duplicating.
"""
import base64
import csv
import logging
from dataclasses import dataclass

import requests

from sf_provider import get_sf
from utils.soql import escape_soql, is_sf_id

logger = logging.getLogger(__name__)

# Single-call base64 inserts are bounded by request/heap size; larger files need
# a multipart upload (not implemented). Flag them instead of failing the run.
DEFAULT_MAX_MB = 35
_CHUNK = 200


@dataclass
class MigrationConfig:
    """Run configuration, built from CLI args or the web form.

    Crosswalk mode: set ``id_map`` (a CSV path) + the column names. External-Id
    mode: leave ``id_map`` blank and set ``parent`` + ``ext_id`` (+ scope via
    ``by``/``where``/``ids_file``).
    """
    id_map: str = ''
    map_old_col: str = 'old_id'
    map_new_col: str = 'new_id'
    parent: str = ''
    ext_id: str = ''
    by: str = 'filter'
    where: str = ''
    ids_file: str = ''
    max_mb: int = DEFAULT_MAX_MB


# ── Pure helpers ──────────────────────────────────────────────────────────────

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
    to the first two columns — so you can point it straight at an existing
    migration spreadsheet (e.g. ``Accommodation__c`` / ``NEW_Accommodation__c``).
    Rows with a blank old or new value are skipped; last value wins on duplicates.
    """
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
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
    target Id and ``unresolved`` maps source parent Id → reason.
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
    """Return the source parent record Ids in scope (filter or list mode)."""
    if cfg.by == 'filter':
        where = cfg.where or 'Id != null'
        rows = _query_all(sf, f"SELECT Id FROM {cfg.parent} WHERE {where}")
        return [r['Id'] for r in rows if r.get('Id')]

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
    return list(dict.fromkeys(ids))


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


# ── Salesforce writes (execute only) ──────────────────────────────────────────

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
    """Read + resolve everything (no writes); return (plan, resolved, unresolved)."""
    if cfg.id_map:
        # Crosswalk mode: the CSV carries old→new parent Ids, so scope (its keys)
        # and remap come straight from it — no external-Id lookups.
        resolved = load_id_map(cfg.id_map, cfg.map_old_col, cfg.map_new_col)
        unresolved = {}
        parent_ids = list(resolved.keys())
        logger.info('Scope: %d parent Id(s) from crosswalk.', len(parent_ids))
    else:
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
        skipped = [p for p in src_parents if p not in resolved]
        plan.append({
            'doc_id': doc_id,
            'meta': meta,
            'target_parents': list(dict.fromkeys(targets)),
            'unresolved_parents': skipped,
            'oversize': meta['size'] > max_bytes,
        })
    return plan, resolved, unresolved


def summarize(plan, unresolved, max_mb=DEFAULT_MAX_MB):
    """Roll a plan up into the counts the UI/CLI show before committing."""
    migrate = [r for r in plan if r['target_parents'] and not r['oversize']]
    no_parent = [r for r in plan if not r['target_parents'] and not r['oversize']]
    oversize = [r for r in plan if r['oversize']]
    total_bytes = sum(r['meta']['size'] for r in migrate)
    return {
        'files_total': len(plan),
        'migrate': len(migrate),
        'migrate_mb': round(total_bytes / 1024 / 1024, 2),
        'no_parent': len(no_parent),
        'oversize': len(oversize),
        'unresolved_parents': len(unresolved),
        'max_mb': max_mb,
    }


def report_rows(plan):
    """Per-file rows for the CSV report / JSON preview table."""
    out = []
    for row in plan:
        m = row['meta']
        action = ('SKIP (too large — needs multipart)' if row['oversize']
                  else 'MIGRATE' if row['target_parents']
                  else 'SKIP (no resolved parent)')
        out.append({
            'source_cv_id': m['id'],
            'title': m['title'],
            'size_bytes': m['size'],
            'resolved_parents': len(row['target_parents']),
            'unresolved_parents': len(row['unresolved_parents']),
            'oversize': row['oversize'],
            'action': action,
        })
    return out


def execute(source_sf, target_sf, plan):
    """Perform the migration for a plan (idempotent). Returns counts.

    Skip if oversize or no parent resolved; reuse the target ContentDocument if
    this source file was already migrated (stamp match); otherwise stream the
    bytes from source and insert into target. Then link the (new or reused)
    document to every resolved target parent.
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
