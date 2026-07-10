import logging
from typing import Optional

from db import get_cursor
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _strip_attributes(records: list) -> list:
    """Remove the SF 'attributes' metadata key from each record."""
    cleaned = []
    for rec in records:
        cleaned.append({k: v for k, v in rec.items() if k != 'attributes'})
    return cleaned


def run_query(org: str, query: str, all_pages: bool = False, user_key: str = '') -> dict:
    """Execute a SOQL query and return cleaned results with column metadata."""
    sf = get_sf(org)
    if all_pages:
        result = sf.query_all(query)
    else:
        result = sf.query(query)

    records = _strip_attributes(result.get('records', []))
    columns = list(records[0].keys()) if records else []

    # Persist to query_history — non-fatal
    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO query_history (user_key, query, org, row_count) "
                "VALUES (%s, %s, %s, %s)",
                (user_key, query, org, result.get('totalSize', 0)),
            )
    except Exception as exc:
        logger.error("run_query: failed to save query_history: %s", exc)

    return {
        'records': records,
        'total_size': result.get('totalSize', 0),
        'done': result.get('done', True),
        'columns': columns,
    }


def list_objects(org: str) -> list:
    """Return all queryable objects for the org, sorted by name."""
    sf = get_sf(org)
    result = sf.restful('sobjects')
    objects = [
        {
            'name': o['name'],
            'label': o.get('label', o['name']),
            'queryable': o.get('queryable', True),
            'custom': o.get('custom', False),
        }
        for o in result.get('sobjects', [])
        if o.get('queryable', True)
    ]
    return sorted(objects, key=lambda o: o['name'])


def list_fields(org: str, object_name: str) -> list:
    """Return field metadata for an object, sorted by name."""
    sf = get_sf(org)
    desc = sf.restful(f'sobjects/{object_name}/describe')
    fields = []
    for f in desc.get('fields', []):
        fields.append({
            'name': f['name'],
            'label': f.get('label', f['name']),
            'type': f.get('type', ''),
            'required': not f.get('nillable', True),
            'external_id': f.get('externalId', False),
            'formula': f.get('calculated', False),
            'picklist_values': [pv['value'] for pv in f.get('picklistValues', [])],
        })
    return sorted(fields, key=lambda f: f['name'])


def get_saved_queries(user_key: str) -> list:
    """Return all saved queries ordered by name."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id, name, query, created_at FROM saved_queries ORDER BY name")
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("get_saved_queries failed: %s", exc)
        return []


def save_query(user_key: str, name: str, query: str) -> dict:
    """Insert a new saved query and return the created row."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO saved_queries (name, query, created_by) "
                "VALUES (%s, %s, %s) RETURNING id, name, query, created_at",
                (name, query, user_key),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
    except Exception as exc:
        logger.error("save_query failed: %s", exc)
        return {}


def delete_saved_query(user_key: str, query_id: int) -> None:
    """Delete a saved query by id."""
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM saved_queries WHERE id = %s", (query_id,))
    except Exception as exc:
        logger.error("delete_saved_query failed id=%s: %s", query_id, exc)


def get_query_history(user_key: str, org: str, limit: int = 25) -> list:
    """Return the most recent queries for this user+org combo."""
    from db import get_cursor, db_available
    if not db_available():
        return []
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, query, org, ran_at, row_count "
                "FROM query_history "
                "WHERE user_key = %s AND org = %s "
                "ORDER BY ran_at DESC LIMIT %s",
                (user_key, org, limit)
            )
            rows = cur.fetchall()
        return [
            {
                'id': r['id'],
                'query': r['query'],
                'org': r['org'],
                'ran_at': r['ran_at'].isoformat() if r['ran_at'] else None,
                'row_count': r['row_count'],
            }
            for r in (rows or [])
        ]
    except Exception as exc:
        logger.error('get_query_history failed: %s', exc)
        return []


def update_record(org: str, object_name: str, record_id: str, field_name: str, value,
                  bypass: bool = False) -> dict:
    """Update a single field on a record and return a confirmation dict."""
    from sf_provider import dml_guard
    sf = get_sf(org)
    try:
        sf_obj = getattr(sf, object_name)
        with dml_guard(sf, bypass=bypass):
            sf_obj.update(record_id, {field_name: value})
    except AttributeError as exc:
        logger.warning("update_record: object %s not found on client: %s", object_name, exc)
    return {
        'updated': True,
        'record_id': record_id,
        'field_name': field_name,
        'new_value': value,
    }
