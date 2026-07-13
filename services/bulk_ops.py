"""Bulk Operations — Delete, Modify, Reassign, Export via Salesforce APIs."""
import csv
import io
import logging

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_PREVIEW_LIMIT = 20
_MAX_BULK_ROWS = 10_000


# ── Query preview (shared) ────────────────────────────────────────────────────

def query_preview(org: str, soql: str, limit: int = _PREVIEW_LIMIT) -> dict:
    """Run a SOQL SELECT and return first N rows + total count estimate."""
    sf = get_sf(org)
    # Inject LIMIT into query if not present
    soql_upper = soql.strip().upper()
    if 'LIMIT' not in soql_upper:
        soql = soql.rstrip(';') + f' LIMIT {limit}'

    result = sf.query(soql)
    records = result.get('records', [])
    total_size = result.get('totalSize', len(records))
    columns = list(records[0].keys()) if records else []
    columns = [c for c in columns if c != 'attributes']
    rows = [{col: r.get(col) for col in columns} for r in records]
    return {'columns': columns, 'rows': rows, 'total': total_size}


# ── Delete ────────────────────────────────────────────────────────────────────

def bulk_delete_preview(org: str, object_name: str, where_clause: str) -> dict:
    """Preview records that would be deleted."""
    soql = f"SELECT Id, Name FROM {object_name} WHERE {where_clause} LIMIT {_PREVIEW_LIMIT}"
    return query_preview(org, soql, limit=_PREVIEW_LIMIT)


def bulk_delete_execute(org: str, object_name: str, where_clause: str,
                        bypass_triggers: bool = False) -> dict:
    """Delete all records matching the WHERE clause."""
    if Config.SHOW_MOCK:
        return {'deleted': 42, 'errors': 0, 'mock': True}

    sf = get_sf(org)
    # Fetch all IDs first
    soql = f"SELECT Id FROM {object_name} WHERE {where_clause} LIMIT {_MAX_BULK_ROWS}"
    result = sf.query_all(soql)
    records = result.get('records', [])
    if not records:
        return {'deleted': 0, 'errors': 0}

    from sf_provider import bulk2_dml, set_bypass_triggers
    if bypass_triggers:
        set_bypass_triggers(sf, True)
    try:
        id_records = [{'Id': r['Id']} for r in records]
        res = bulk2_dml(sf, object_name, 'delete', id_records)
    finally:
        if bypass_triggers:
            set_bypass_triggers(sf, False)

    return {'deleted': res['succeeded'], 'errors': res['failed'], 'total': len(records),
            'truncated': len(records) >= _MAX_BULK_ROWS, 'cap': _MAX_BULK_ROWS}


# ── Modify (bulk field update) ────────────────────────────────────────────────

def bulk_modify_preview(org: str, object_name: str, where_clause: str,
                        field_name: str, new_value: str) -> dict:
    """Preview records that would be modified."""
    soql = f"SELECT Id, {field_name} FROM {object_name} WHERE {where_clause} LIMIT {_PREVIEW_LIMIT}"
    return query_preview(org, soql, limit=_PREVIEW_LIMIT)


def bulk_modify_execute(org: str, object_name: str, where_clause: str,
                        field_updates: dict, bypass_triggers: bool = False) -> dict:
    """Update field_updates={field: value} on all records matching where_clause."""
    if Config.SHOW_MOCK:
        return {'updated': 37, 'errors': 0, 'mock': True}

    sf = get_sf(org)
    soql = f"SELECT Id FROM {object_name} WHERE {where_clause} LIMIT {_MAX_BULK_ROWS}"
    result = sf.query_all(soql)
    records = result.get('records', [])
    if not records:
        return {'updated': 0, 'errors': 0}

    from sf_provider import bulk2_dml, set_bypass_triggers
    if bypass_triggers:
        set_bypass_triggers(sf, True)
    try:
        update_records = [{'Id': r['Id'], **field_updates} for r in records]
        res = bulk2_dml(sf, object_name, 'update', update_records)
    finally:
        if bypass_triggers:
            set_bypass_triggers(sf, False)

    return {'updated': res['succeeded'], 'errors': res['failed'], 'total': len(records),
            'truncated': len(records) >= _MAX_BULK_ROWS, 'cap': _MAX_BULK_ROWS}


# ── Reassign ──────────────────────────────────────────────────────────────────

def search_users(org: str, query: str = '') -> list:
    """Search active users for the owner picker."""
    sf = get_sf(org)
    where = f"AND (Name LIKE '%{query}%' OR Username LIKE '%{query}%')" if query else ''
    soql = f"SELECT Id, Name, Username FROM User WHERE IsActive = true {where} ORDER BY Name LIMIT 20"
    result = sf.query(soql)
    return [{'id': r['Id'], 'name': r.get('Name', ''), 'username': r.get('Username', '')}
            for r in result.get('records', [])]


def bulk_reassign_preview(org: str, object_name: str, where_clause: str) -> dict:
    """Preview records to be reassigned."""
    soql = f"SELECT Id, Name, OwnerId FROM {object_name} WHERE {where_clause} LIMIT {_PREVIEW_LIMIT}"
    return query_preview(org, soql, limit=_PREVIEW_LIMIT)


def bulk_reassign_execute(org: str, object_name: str, where_clause: str,
                          new_owner_id: str, bypass_triggers: bool = False) -> dict:
    """Reassign ownership of matching records to new_owner_id."""
    if Config.SHOW_MOCK:
        return {'reassigned': 15, 'errors': 0, 'mock': True}

    sf = get_sf(org)
    soql = f"SELECT Id FROM {object_name} WHERE {where_clause} LIMIT {_MAX_BULK_ROWS}"
    result = sf.query_all(soql)
    records = result.get('records', [])
    if not records:
        return {'reassigned': 0, 'errors': 0}

    from sf_provider import bulk2_dml, set_bypass_triggers
    if bypass_triggers:
        set_bypass_triggers(sf, True)
    try:
        update_records = [{'Id': r['Id'], 'OwnerId': new_owner_id} for r in records]
        res = bulk2_dml(sf, object_name, 'update', update_records)
    finally:
        if bypass_triggers:
            set_bypass_triggers(sf, False)

    return {'reassigned': res['succeeded'], 'errors': res['failed'], 'total': len(records),
            'truncated': len(records) >= _MAX_BULK_ROWS, 'cap': _MAX_BULK_ROWS}


# ── Export ────────────────────────────────────────────────────────────────────

def export_to_csv(org: str, soql: str, all_pages: bool = True) -> str:
    """Run SOQL and return results as a CSV string."""
    sf = get_sf(org)
    if all_pages:
        result = sf.query_all(soql)
    else:
        result = sf.query(soql)

    records = result.get('records', [])
    if not records:
        return ''

    columns = [k for k in records[0].keys() if k != 'attributes']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for r in records:
        writer.writerow({k: r.get(k, '') for k in columns})
    return buf.getvalue()
