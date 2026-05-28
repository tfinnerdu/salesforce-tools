"""Source ingestion — turn a source spec into a list of row dicts.

The key_map engine consumes ``list[dict]`` and is agnostic to where the rows
came from. This module is the seam that produces those rows from a declarative
``source_spec``:

    {"mode": "inline", "rows": [{...}, ...]}
    {"mode": "json",   "data": "<json string>", "records_path": "applicants"}

Phase 3 will add:
    {"mode": "csv", "data": "<csv text>"}                      (paste/upload)
    {"mode": "sql", "query": "SELECT ...", "connection": ...}  (live SQL Server)

Until then, those modes raise a clear "not yet available" error rather than
pretending to work.
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_MODES = {'inline', 'json'}
PLANNED_MODES = {'csv', 'sql'}


def load_source_rows(source_spec: dict, org: str = 'dev') -> list:
    """Resolve a source_spec into a list of flat row dicts.

    Raises ValueError for an unknown/unsupported mode or malformed spec.
    """
    if not isinstance(source_spec, dict):
        raise ValueError('source must be an object with a "mode"')
    mode = (source_spec.get('mode') or '').strip().lower()
    if not mode:
        raise ValueError('source.mode is required')

    if mode == 'inline':
        rows = source_spec.get('rows')
        if not isinstance(rows, list):
            raise ValueError('source.rows must be a list for mode "inline"')
        return [dict(r) for r in rows]

    if mode == 'json':
        return _load_json(source_spec)

    if mode in PLANNED_MODES:
        raise ValueError(
            f"source mode '{mode}' is not available yet (planned for a later "
            f"phase). Use 'inline' or 'json' for now."
        )

    raise ValueError(
        f"Unknown source mode '{mode}' — must be one of {sorted(SUPPORTED_MODES)}"
    )


def _load_json(source_spec: dict) -> list:
    """Parse a JSON string into rows, flattening nested objects to dotted keys.

    Row discovery:
      - top-level list                       → each element is a row
      - top-level dict + records_path given  → navigate to that list
      - top-level dict with a single list value → use that list
      - top-level dict otherwise             → a single row
    """
    raw = source_spec.get('data')
    if raw is None or raw == '':
        raise ValueError('source.data (JSON string) is required for mode "json"')
    if isinstance(raw, (dict, list)):
        parsed = raw  # already-parsed payloads are accepted as-is
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f'source.data is not valid JSON: {exc}') from exc

    records = _find_records(parsed, source_spec.get('records_path'))
    return [_flatten(r) for r in records]


def _find_records(parsed: Any, records_path: str = None) -> list:
    if records_path:
        node = parsed
        for part in str(records_path).split('.'):
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        if not isinstance(node, list):
            raise ValueError(
                f"records_path '{records_path}' did not resolve to a list"
            )
        return node
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        list_values = [v for v in parsed.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
        return [parsed]   # single record
    raise ValueError('JSON must be an object or an array of objects')


def _flatten(record: Any, prefix: str = '') -> dict:
    """Flatten nested objects into dotted keys. Lists and scalars are kept as-is
    (list-of-objects fanout is a deliberate non-goal for this phase — a nested
    array stays a JSON-serialisable value the mapper can ignore or stringify)."""
    if not isinstance(record, dict):
        return {prefix.rstrip('.') or 'value': record}
    out: dict = {}
    for key, value in record.items():
        full = f'{prefix}{key}'
        if isinstance(value, dict):
            out.update(_flatten(value, prefix=f'{full}.'))
        else:
            out[full] = value
    return out
