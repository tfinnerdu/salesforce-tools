import json, logging
from datetime import datetime, timezone
import psycopg2.extras
from db import get_cursor, db_available
from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)

def _ensure_table():
    if not db_available(): return
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_snapshots (
                id SERIAL PRIMARY KEY,
                org VARCHAR(32) NOT NULL,
                sobject VARCHAR(128) NOT NULL,
                snapshot_label VARCHAR(128),
                fields_json TEXT NOT NULL,
                captured_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

def take_snapshot(org: str, sobject: str, label: str = None) -> dict:
    """Describe sobject and store field metadata as a snapshot."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        fields = _mock_fields(sobject)
    else:
        desc = sf.Account.describe() if sobject == 'Account' else getattr(sf, sobject).describe()
        fields = [
            {
                'name': f['name'],
                'label': f['label'],
                'type': f['type'],
                'length': f.get('length'),
                'required': not f['nillable'] and not f['defaultedOnCreate'],
                'unique': f.get('unique', False),
                'externalId': f.get('externalId', False),
                'custom': f.get('custom', False),
            }
            for f in desc['fields']
        ]
    _ensure_table()
    label = label or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    if db_available():
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO schema_snapshots (org, sobject, snapshot_label, fields_json) VALUES (%s,%s,%s,%s) RETURNING id",
                (org, sobject, label, json.dumps(fields))
            )
            snap_id = cur.fetchone()['id']
    else:
        snap_id = 0
    return {'id': snap_id, 'org': org, 'sobject': sobject, 'label': label, 'field_count': len(fields)}

def list_snapshots(org: str = None, sobject: str = None) -> list:
    _ensure_table()
    if not db_available():
        return _mock_snapshot_list()
    with get_cursor() as cur:
        conditions, params = [], []
        if org: conditions.append('org=%s'); params.append(org)
        if sobject: conditions.append('sobject=%s'); params.append(sobject)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        cur.execute(f"SELECT id, org, sobject, snapshot_label, captured_at, length(fields_json) as size FROM schema_snapshots {where} ORDER BY captured_at DESC LIMIT 50", params)
        return [dict(r) for r in cur.fetchall()]

def diff_snapshots(snap_id_a: int, snap_id_b: int) -> dict:
    """Return added/removed/changed fields between two snapshots."""
    _ensure_table()
    if not db_available():
        return _mock_diff()
    with get_cursor() as cur:
        cur.execute("SELECT org, sobject, snapshot_label, captured_at, fields_json FROM schema_snapshots WHERE id=%s", (snap_id_a,))
        row_a = cur.fetchone()
        cur.execute("SELECT org, sobject, snapshot_label, captured_at, fields_json FROM schema_snapshots WHERE id=%s", (snap_id_b,))
        row_b = cur.fetchone()
    if not row_a or not row_b:
        raise ValueError('Snapshot not found')
    fields_a = {f['name']: f for f in json.loads(row_a['fields_json'])}
    fields_b = {f['name']: f for f in json.loads(row_b['fields_json'])}
    added = [fields_b[k] for k in fields_b if k not in fields_a]
    removed = [fields_a[k] for k in fields_a if k not in fields_b]
    changed = []
    for k in fields_a:
        if k in fields_b and fields_a[k] != fields_b[k]:
            changed.append({'name': k, 'before': fields_a[k], 'after': fields_b[k]})
    return {
        'snap_a': {'id': snap_id_a, 'label': row_a['snapshot_label'], 'captured_at': str(row_a['captured_at'])},
        'snap_b': {'id': snap_id_b, 'label': row_b['snapshot_label'], 'captured_at': str(row_b['captured_at'])},
        'sobject': row_a['sobject'],
        'added': added, 'removed': removed, 'changed': changed,
        'summary': {'added': len(added), 'removed': len(removed), 'changed': len(changed)},
    }

def delete_snapshot(snap_id: int) -> bool:
    _ensure_table()
    if not db_available(): return False
    with get_cursor() as cur:
        cur.execute("DELETE FROM schema_snapshots WHERE id=%s", (snap_id,))
    return True

def _mock_fields(sobject: str) -> list:
    base = [
        {'name': 'Id', 'label': 'Record ID', 'type': 'id', 'length': 18, 'required': True, 'unique': True, 'externalId': False, 'custom': False},
        {'name': 'Name', 'label': 'Full Name', 'type': 'string', 'length': 255, 'required': True, 'unique': False, 'externalId': False, 'custom': False},
        {'name': 'CreatedDate', 'label': 'Created Date', 'type': 'datetime', 'length': None, 'required': False, 'unique': False, 'externalId': False, 'custom': False},
    ]
    if sobject == 'Account':
        base += [
            {'name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'string', 'length': 64, 'required': False, 'unique': True, 'externalId': True, 'custom': True},
            {'name': 'Ethos_Guid__c', 'label': 'Ethos GUID', 'type': 'string', 'length': 36, 'required': False, 'unique': True, 'externalId': True, 'custom': True},
        ]
    return base

def _mock_snapshot_list() -> list:
    return [
        {'id': 1, 'org': 'prod', 'sobject': 'Account', 'snapshot_label': '2026-05-01 06:00 UTC', 'captured_at': '2026-05-01T06:00:00Z', 'size': 4200},
        {'id': 2, 'org': 'prod', 'sobject': 'Account', 'snapshot_label': '2026-05-15 06:00 UTC', 'captured_at': '2026-05-15T06:00:00Z', 'size': 4312},
    ]

def _mock_diff() -> dict:
    return {
        'snap_a': {'id': 1, 'label': '2026-05-01 06:00 UTC', 'captured_at': '2026-05-01T06:00:00Z'},
        'snap_b': {'id': 2, 'label': '2026-05-15 06:00 UTC', 'captured_at': '2026-05-15T06:00:00Z'},
        'sobject': 'Account',
        'added': [{'name': 'New_Field__c', 'label': 'New Field', 'type': 'string', 'length': 128, 'required': False, 'unique': False, 'externalId': False, 'custom': True}],
        'removed': [],
        'changed': [{'name': 'SIS_ID__c', 'before': {'unique': False}, 'after': {'unique': True}}],
        'summary': {'added': 1, 'removed': 0, 'changed': 1},
    }
