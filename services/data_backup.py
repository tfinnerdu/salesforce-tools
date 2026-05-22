"""Data Backup — point-in-time CSV snapshots of key Salesforce objects.

The bulk Data Ops tools (Delete, Modify, Tune) can change data at scale and
the Recycle Bin only soft-deletes for 15 days. A backup run exports every
configured object to CSV (all queryable fields), gzips it, and stores it in
Postgres so a known-good recovery point always exists. Retention prunes old
runs. Restore is a separate, later feature — this module only captures.
"""
import csv
import gzip
import io
import logging
import zipfile
from datetime import datetime, timezone

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

# Migration-critical objects backed up by default. Editable from the UI.
DEFAULT_BACKUP_OBJECTS = [
    'Account', 'Contact', 'Individual',
    'ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress',
]

# Field types that are not safely or usefully exported in a flat CSV.
_SKIP_FIELD_TYPES = {'base64', 'address', 'location'}

_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS backup_runs (
    id            SERIAL PRIMARY KEY,
    org           TEXT,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    status        TEXT DEFAULT 'success',
    trigger       TEXT DEFAULT 'manual',
    object_count  INTEGER DEFAULT 0,
    total_records INTEGER DEFAULT 0,
    error         TEXT
);
"""

_FILES_DDL = """
CREATE TABLE IF NOT EXISTS backup_files (
    id           SERIAL PRIMARY KEY,
    run_id       INTEGER REFERENCES backup_runs(id) ON DELETE CASCADE,
    object_name  TEXT,
    record_count INTEGER DEFAULT 0,
    csv_gz       BYTEA
);
"""


def _ensure_tables() -> None:
    from db import get_cursor
    with get_cursor() as cur:
        cur.execute(_RUNS_DDL)
        cur.execute(_FILES_DDL)


# ── Export one object ─────────────────────────────────────────────────────────

def _export_object(sf, object_name: str) -> tuple:
    """Return (csv_text, record_count) for every queryable field of an object."""
    desc = sf.restful(f'sobjects/{object_name}/describe')
    fields = [
        f['name'] for f in desc.get('fields', [])
        if f.get('type') not in _SKIP_FIELD_TYPES
    ]
    if not fields:
        return '', 0
    soql = f"SELECT {', '.join(fields)} FROM {object_name}"
    result = sf.query_all(soql)
    records = result.get('records', [])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for r in records:
        writer.writerow({f: r.get(f, '') for f in fields})
    return buf.getvalue(), len(records)


# ── Run a backup ──────────────────────────────────────────────────────────────

def run_backup(org: str, objects: list = None, trigger: str = 'manual') -> dict:
    """Export each object to CSV, store the run in Postgres, prune old runs.

    Returns a manifest: {run_id, org, status, total_records, objects:[{object,
    records}], persisted, errors:[...]}.
    """
    objects = objects or DEFAULT_BACKUP_OBJECTS
    sf = get_sf(org)

    manifest_objects = []
    files = []          # (object_name, record_count, csv_text)
    errors = []
    total_records = 0
    for obj in objects:
        try:
            csv_text, count = _export_object(sf, obj)
            files.append((obj, count, csv_text))
            manifest_objects.append({'object': obj, 'records': count})
            total_records += count
        except Exception as exc:
            logger.warning('backup: export of %s failed: %s', obj, exc)
            errors.append({'object': obj, 'error': str(exc)})
            manifest_objects.append({'object': obj, 'records': None, 'error': str(exc)})

    status = 'success' if not errors else ('partial' if files else 'error')
    run_id, persisted = _store_run(org, trigger, status, total_records, files,
                                   '; '.join(e['error'] for e in errors) or None)
    if persisted:
        _prune(Config.BACKUP_RETAIN)

    return {
        'run_id': run_id,
        'org': org,
        'status': status,
        'trigger': trigger,
        'object_count': len(files),
        'total_records': total_records,
        'objects': manifest_objects,
        'errors': errors,
        'persisted': persisted,
    }


def _store_run(org, trigger, status, total_records, files, error) -> tuple:
    """Persist a run + its files. Returns (run_id, persisted_bool)."""
    try:
        from db import get_cursor, db_available
        if not db_available():
            return None, False
        _ensure_tables()
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO backup_runs (org, status, trigger, object_count, "
                "total_records, error) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (org, status, trigger, len(files), total_records, error),
            )
            run_id = cur.fetchone()['id']
            for object_name, count, csv_text in files:
                cur.execute(
                    "INSERT INTO backup_files (run_id, object_name, record_count, csv_gz) "
                    "VALUES (%s, %s, %s, %s)",
                    (run_id, object_name, count,
                     gzip.compress(csv_text.encode('utf-8'))),
                )
        return run_id, True
    except Exception as exc:
        logger.warning('backup _store_run failed: %s', exc)
        return None, False


def _prune(keep: int) -> None:
    """Keep only the most recent `keep` runs (files cascade-delete)."""
    try:
        from db import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "DELETE FROM backup_runs WHERE id NOT IN "
                "(SELECT id FROM backup_runs ORDER BY started_at DESC LIMIT %s)",
                (keep,),
            )
    except Exception as exc:
        logger.warning('backup _prune failed: %s', exc)


# ── Read / download ───────────────────────────────────────────────────────────

def list_backups(org: str = None, limit: int = 30) -> list:
    """Return recent backup runs (newest first)."""
    try:
        from db import get_cursor, db_available
        if not db_available():
            return []
        _ensure_tables()
        with get_cursor() as cur:
            if org:
                cur.execute(
                    "SELECT id, org, started_at, status, trigger, object_count, "
                    "total_records, error FROM backup_runs WHERE org = %s "
                    "ORDER BY started_at DESC LIMIT %s", (org, limit))
            else:
                cur.execute(
                    "SELECT id, org, started_at, status, trigger, object_count, "
                    "total_records, error FROM backup_runs "
                    "ORDER BY started_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
        return [{
            'id': r['id'], 'org': r['org'], 'status': r['status'],
            'trigger': r['trigger'], 'object_count': r['object_count'],
            'total_records': r['total_records'], 'error': r['error'],
            'started_at': r['started_at'].isoformat()
            if hasattr(r['started_at'], 'isoformat') else str(r['started_at']),
        } for r in rows]
    except Exception as exc:
        logger.warning('list_backups failed: %s', exc)
        return []


def build_archive(run_id: int) -> tuple:
    """Build a ZIP of one run's CSVs. Returns (zip_bytes, filename).

    Raises ValueError if the run is not found.
    """
    from db import get_cursor, db_available
    if not db_available():
        raise ValueError('Backup storage (database) is not available')
    _ensure_tables()
    with get_cursor() as cur:
        cur.execute("SELECT org, started_at FROM backup_runs WHERE id = %s", (run_id,))
        run = cur.fetchone()
        if not run:
            raise ValueError(f'Backup run {run_id} not found')
        cur.execute(
            "SELECT object_name, csv_gz FROM backup_files WHERE run_id = %s "
            "ORDER BY object_name", (run_id,))
        files = cur.fetchall()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            csv_bytes = gzip.decompress(bytes(f['csv_gz'])) if f['csv_gz'] else b''
            zf.writestr(f"{f['object_name']}.csv", csv_bytes)
    stamp = run['started_at']
    stamp_str = stamp.strftime('%Y%m%d_%H%M%S') if hasattr(stamp, 'strftime') else str(run_id)
    return buf.getvalue(), f"backup_{run['org']}_{stamp_str}.zip"
