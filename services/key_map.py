"""Source → Salesforce Key Map engine.

A key_map is a reusable spec that transforms source rows (from a SQL result
or a JSON document) into Salesforce records of one SObject. Three layers:

1. **FK lookups** — resolve foreign keys on the target SObject by looking up
   another SObject by an external-ID-style field (typically SIS_ID__c).
2. **Family routing** — pick which family of variants applies to each source
   row based on column-equals-value rules.
3. **Variant overlay** — for each variant in the applicable family, produce
   one output row that's the resolved-FK base merged with the variant's
   ``overlay_json`` (target_field → literal_value).

The engine is preview-only in v1: it returns the would-be-inserted rows
plus an ``unresolved_fks`` list. Nothing writes to Salesforce until a
follow-up phase wires up the upsert path.

PTATs are the first consumer but the model is deliberately generic — any
"one source row → N SF records via FK resolution and family fanout" pattern
fits.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from config import Config
from db import db_available, get_cursor
from utils.soql import escape_soql

logger = logging.getLogger(__name__)


# ── CRUD: key_maps ───────────────────────────────────────────────────────────

def list_key_maps() -> list:
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            'SELECT id, name, description, target_sobject, created_by, '
            '       created_at, updated_at '
            'FROM key_maps ORDER BY LOWER(name)'
        )
        return [dict(r) for r in cur.fetchall()]


def get_key_map(key_map_id: int, include_children: bool = True) -> Optional[dict]:
    """Return one key_map, optionally with its fk_lookups, families, and variants."""
    if not db_available():
        return None
    with get_cursor() as cur:
        cur.execute(
            'SELECT id, name, description, target_sobject, created_by, '
            '       created_at, updated_at '
            'FROM key_maps WHERE id = %s',
            (key_map_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        km = dict(row)
        if include_children:
            km['fk_lookups'] = _list_fk_lookups(cur, key_map_id)
            km['families'] = _list_families_with_variants(cur, key_map_id)
    return km


def create_key_map(name: str, description: str, target_sobject: str,
                   created_by: str = 'system') -> dict:
    if not name or not name.strip():
        raise ValueError('Key map name is required')
    if not target_sobject or not target_sobject.strip():
        raise ValueError('target_sobject is required')
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO key_maps (name, description, target_sobject, created_by) '
            'VALUES (%s, %s, %s, %s) '
            'RETURNING id, name, description, target_sobject, created_by, '
            '          created_at, updated_at',
            (name.strip(), description, target_sobject.strip(), created_by),
        )
        return dict(cur.fetchone())


def update_key_map(key_map_id: int, name: str, description: str,
                   target_sobject: str) -> Optional[dict]:
    if not name or not name.strip():
        raise ValueError('Key map name is required')
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'UPDATE key_maps '
            'SET name = %s, description = %s, target_sobject = %s, updated_at = NOW() '
            'WHERE id = %s '
            'RETURNING id, name, description, target_sobject, created_by, '
            '          created_at, updated_at',
            (name.strip(), description, target_sobject.strip(), key_map_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def delete_key_map(key_map_id: int) -> bool:
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM key_maps WHERE id = %s', (key_map_id,))
        return cur.rowcount > 0


# ── CRUD: fk_lookups ─────────────────────────────────────────────────────────

def add_fk_lookup(key_map_id: int, source_column: str, target_field: str,
                  lookup_sobject: str, lookup_field: str = 'SIS_ID__c',
                  position: int = 0) -> dict:
    for v, label in [(source_column, 'source_column'),
                     (target_field, 'target_field'),
                     (lookup_sobject, 'lookup_sobject'),
                     (lookup_field, 'lookup_field')]:
        if not v or not v.strip():
            raise ValueError(f'{label} is required')
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO key_map_fk_lookups '
            '  (key_map_id, source_column, target_field, lookup_sobject, '
            '   lookup_field, position) '
            'VALUES (%s, %s, %s, %s, %s, %s) '
            'RETURNING id, key_map_id, source_column, target_field, '
            '          lookup_sobject, lookup_field, position',
            (key_map_id, source_column.strip(), target_field.strip(),
             lookup_sobject.strip(), lookup_field.strip(), position),
        )
        return dict(cur.fetchone())


def delete_fk_lookup(lookup_id: int) -> bool:
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM key_map_fk_lookups WHERE id = %s', (lookup_id,))
        return cur.rowcount > 0


# ── CRUD: families + variants ────────────────────────────────────────────────

def add_family(key_map_id: int, name: str, routing: Optional[dict] = None,
               position: int = 0) -> dict:
    if not name or not name.strip():
        raise ValueError('Family name is required')
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    routing = routing or {}
    _validate_routing_shape(routing, 'routing')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO key_map_families (key_map_id, name, routing_json, position) '
            'VALUES (%s, %s, %s, %s) '
            'RETURNING id, key_map_id, name, routing_json, position',
            (key_map_id, name.strip(), json.dumps(routing), position),
        )
        return _serialize_family(cur.fetchone())


def delete_family(family_id: int) -> bool:
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM key_map_families WHERE id = %s', (family_id,))
        return cur.rowcount > 0


def add_variant(family_id: int, name: str, overlay: dict,
                applies_when: Optional[dict] = None, position: int = 0) -> dict:
    if not name or not name.strip():
        raise ValueError('Variant name is required')
    if not isinstance(overlay, dict):
        raise ValueError('overlay must be an object')
    applies_when = applies_when or {}
    _validate_routing_shape(applies_when, 'applies_when')
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO key_map_variants '
            '  (family_id, name, overlay_json, applies_when, position) '
            'VALUES (%s, %s, %s, %s, %s) '
            'RETURNING id, family_id, name, overlay_json, applies_when, position',
            (family_id, name.strip(), json.dumps(overlay),
             json.dumps(applies_when), position),
        )
        return _serialize_variant(cur.fetchone())


def delete_variant(variant_id: int) -> bool:
    if not db_available():
        raise RuntimeError('Key maps require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM key_map_variants WHERE id = %s', (variant_id,))
        return cur.rowcount > 0


# ── Resolution + expansion engine ────────────────────────────────────────────

def resolve_and_expand(key_map_id: int, source_rows: list, org: str = 'dev',
                       sf_client=None) -> dict:
    """Run a preview pass against ``source_rows`` for a given key_map.

    Returns ``{output_rows, unresolved_fks, summary}``. Does not write to
    Salesforce — the FK lookups are reads only.

    ``sf_client`` is injected for testability; production callers pass
    ``None`` and the engine reaches for ``sf_provider.get_sf(org)``.
    """
    key_map = get_key_map(key_map_id, include_children=True)
    if key_map is None:
        raise ValueError(f'Key map {key_map_id} not found')

    fk_lookups = key_map.get('fk_lookups') or []
    families = key_map.get('families') or []

    if not families:
        raise ValueError(
            f"Key map '{key_map['name']}' has no families defined — "
            f"nothing to expand into."
        )

    # 1. Resolve every FK in one pass (cached per distinct value).
    fk_resolution_map, unresolved = _resolve_all_fks(
        source_rows, fk_lookups, org, sf_client,
    )

    # 2. For each source row, pick a family then fan out variants.
    output_rows: list = []
    family_counts: dict = defaultdict(int)
    variant_counts: dict = defaultdict(int)
    skipped_no_family = 0

    for row_idx, source_row in enumerate(source_rows):
        family = _family_for_row(families, source_row)
        if family is None:
            skipped_no_family += 1
            continue
        family_counts[family['name']] += 1

        # Build the base of resolved FKs (target_field → resolved Id or None).
        base: dict = {}
        for fk in fk_lookups:
            src_val = source_row.get(fk['source_column'])
            if src_val is None:
                base[fk['target_field']] = None
                continue
            base[fk['target_field']] = fk_resolution_map.get(
                (fk['lookup_sobject'], fk['lookup_field'], src_val)
            )

        for variant in family['variants']:
            if not _row_matches(variant.get('applies_when') or {}, source_row):
                continue
            row_out = dict(base)
            row_out.update(variant.get('overlay_json') or {})
            row_out['_source_row_idx'] = row_idx
            row_out['_family'] = family['name']
            row_out['_variant'] = variant['name']
            output_rows.append(row_out)
            variant_counts[f"{family['name']}::{variant['name']}"] += 1

    return {
        'output_rows': output_rows,
        'unresolved_fks': unresolved,
        'summary': {
            'source_count': len(source_rows),
            'output_count': len(output_rows),
            'skipped_no_family': skipped_no_family,
            'unresolved_count': len(unresolved),
            'families': dict(family_counts),
            'variants': dict(variant_counts),
        },
    }


def save_run(key_map_id: int, org: str, result: dict) -> Optional[int]:
    """Persist a preview run for later download/inspection."""
    if not db_available():
        return None
    summary = result.get('summary') or {}
    status = 'success' if not result.get('unresolved_fks') else 'partial'
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO key_map_runs '
            '  (key_map_id, org, finished_at, status, source_count, '
            '   output_count, unresolved_fks, output_rows, summary) '
            'VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s) '
            'RETURNING id',
            (key_map_id, org, status,
             summary.get('source_count', 0),
             summary.get('output_count', 0),
             json.dumps(result.get('unresolved_fks') or []),
             json.dumps(result.get('output_rows') or []),
             json.dumps(summary)),
        )
        return cur.fetchone()['id']


# ── Internals ────────────────────────────────────────────────────────────────

def _resolve_all_fks(source_rows: list, fk_lookups: list, org: str,
                     sf_client) -> tuple:
    """Single-pass FK resolution. Returns ``(resolution_map, unresolved)``.

    ``resolution_map`` is ``{(sobject, field, value): id_or_None}``.
    ``unresolved`` lists each (row_idx, source_column, target_field, value)
    that couldn't be resolved to an SF record.
    """
    # Collect distinct (sobject, field, value) triples across all rows.
    needed: dict = defaultdict(set)
    for row in source_rows:
        for fk in fk_lookups:
            val = row.get(fk['source_column'])
            if val is None or val == '':
                continue
            needed[(fk['lookup_sobject'], fk['lookup_field'])].add(val)

    resolution_map: dict = {}
    if needed:
        if Config.SHOW_MOCK:
            # Demo mode: synthesise stable fake Ids so the preview is
            # end-to-end runnable without ever reaching Salesforce.
            for (sobj, field), values in needed.items():
                for v in values:
                    resolution_map[(sobj, field, v)] = f'MOCK_{sobj}_{v}'
        else:
            sf = sf_client
            if sf is None:
                from sf_provider import get_sf
                sf = get_sf(org)
            for (sobj, field), values in needed.items():
                ids_by_value = _bulk_lookup(sf, sobj, field, list(values))
                for v in values:
                    resolution_map[(sobj, field, v)] = ids_by_value.get(v)

    # Now scan source rows for any that didn't resolve.
    unresolved: list = []
    for row_idx, row in enumerate(source_rows):
        for fk in fk_lookups:
            val = row.get(fk['source_column'])
            if val is None or val == '':
                continue
            resolved = resolution_map.get(
                (fk['lookup_sobject'], fk['lookup_field'], val)
            )
            if not resolved:
                unresolved.append({
                    'row_idx': row_idx,
                    'source_column': fk['source_column'],
                    'target_field': fk['target_field'],
                    'lookup_sobject': fk['lookup_sobject'],
                    'lookup_field': fk['lookup_field'],
                    'value': val,
                })
    return resolution_map, unresolved


def _bulk_lookup(sf, sobject: str, field: str, values: list) -> dict:
    """Resolve ``{value: Id}`` for a single SObject + field in one SOQL pass.

    Chunks IN-clauses so very large value lists don't blow the 100 KB SOQL
    limit. Returns only the values that matched a record.
    """
    out: dict = {}
    CHUNK = 200
    for i in range(0, len(values), CHUNK):
        chunk = values[i:i + CHUNK]
        # Quote string literals with full SOQL escaping (backslash + quote).
        literals = ', '.join("'" + escape_soql(v) + "'" for v in chunk)
        soql = f"SELECT Id, {field} FROM {sobject} WHERE {field} IN ({literals})"
        try:
            res = sf.query(soql)
        except Exception as exc:
            logger.warning('FK lookup failed for %s.%s: %s', sobject, field, exc)
            continue
        for record in res.get('records') or []:
            key = record.get(field)
            if key is not None:
                out[key] = record.get('Id')
    return out


def _family_for_row(families: list, row: dict) -> Optional[dict]:
    """Return the first family whose routing matches the row, falling back to
    a family with empty routing (the default). None if no family applies."""
    default = None
    for fam in families:
        routing = fam.get('routing_json') or {}
        if not routing.get('match'):
            if default is None:
                default = fam
            continue
        if _row_matches(routing, row):
            return fam
    return default


def _row_matches(rule: dict, row: dict) -> bool:
    """Evaluate a routing/applies_when rule against a source row.

    Rule shape: ``{"match": [{"source_column": "X", "equals": "Y"}, ...]}``.
    All clauses must match (AND). Empty rule = match-everything.
    """
    clauses = (rule or {}).get('match') or []
    if not clauses:
        return True
    for clause in clauses:
        col = clause.get('source_column')
        expected = clause.get('equals')
        if col is None:
            continue
        if row.get(col) != expected:
            return False
    return True


def _validate_routing_shape(rule: dict, label: str) -> None:
    """Raise ValueError if a routing/applies_when rule is malformed."""
    if not isinstance(rule, dict):
        raise ValueError(f'{label} must be an object')
    clauses = rule.get('match')
    if clauses is None:
        return  # empty rule = match-everything; fine
    if not isinstance(clauses, list):
        raise ValueError(f'{label}.match must be a list')
    for i, clause in enumerate(clauses, start=1):
        if not isinstance(clause, dict):
            raise ValueError(f'{label}.match[{i}] must be an object')
        if 'source_column' not in clause or 'equals' not in clause:
            raise ValueError(
                f'{label}.match[{i}] requires source_column + equals'
            )


def _list_fk_lookups(cur, key_map_id: int) -> list:
    cur.execute(
        'SELECT id, key_map_id, source_column, target_field, lookup_sobject, '
        '       lookup_field, position '
        'FROM key_map_fk_lookups WHERE key_map_id = %s ORDER BY position, id',
        (key_map_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def _list_families_with_variants(cur, key_map_id: int) -> list:
    cur.execute(
        'SELECT id, key_map_id, name, routing_json, position '
        'FROM key_map_families WHERE key_map_id = %s ORDER BY position, id',
        (key_map_id,),
    )
    families = [_serialize_family(r) for r in cur.fetchall()]
    for fam in families:
        cur.execute(
            'SELECT id, family_id, name, overlay_json, applies_when, position '
            'FROM key_map_variants WHERE family_id = %s ORDER BY position, id',
            (fam['id'],),
        )
        fam['variants'] = [_serialize_variant(r) for r in cur.fetchall()]
    return families


def _serialize_family(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    d['routing_json'] = _maybe_parse_json(d.get('routing_json'))
    return d


def _serialize_variant(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    d['overlay_json'] = _maybe_parse_json(d.get('overlay_json'))
    d['applies_when'] = _maybe_parse_json(d.get('applies_when'))
    return d


def _maybe_parse_json(value):
    """psycopg2's JSONB column comes back parsed; psycopg2-binary may return
    a raw string in some configurations. Handle both shapes defensively."""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
