"""Source ingestion — turn a source spec into a list of row dicts.

The key_map engine consumes ``list[dict]`` and is agnostic to where the rows
came from. This module is the seam that produces those rows from a declarative
``source_spec``:

    {"mode": "inline", "rows": [{...}, ...]}
    {"mode": "json",   "data": "<json string>", "records_path": "applicants"}
    {"mode": "csv",    "data": "<csv or tsv text>"}
    {"mode": "sql",    "query": "SELECT ...", "max_rows": 100000}

The ``sql`` mode runs a read-only query against the Colleague SQL Server via
the shared services.sqlserver connection (the same one the Join Builder uses —
standard MS ODBC driver, no Devart).
"""
import csv as _csv
import io
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_MODES = {'inline', 'json', 'csv', 'sql'}


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

    if mode == 'csv':
        return _load_csv(source_spec)

    if mode == 'sql':
        return _load_sql(source_spec)

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


def _load_csv(source_spec: dict) -> list:
    """Parse pasted/uploaded CSV or TSV text into rows. The first line is the
    header. Delimiter is sniffed (comma vs tab); falls back to comma."""
    text = source_spec.get('data')
    if not text or not str(text).strip():
        raise ValueError('source.data (CSV/TSV text) is required for mode "csv"')
    text = str(text)
    sample = text[:4096]
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=',\t;|')
    except _csv.Error:
        dialect = _csv.excel  # default comma dialect
    reader = _csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        # DictReader keys/values can carry surrounding whitespace; trim both.
        rows.append({(k or '').strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in row.items() if k is not None})
    return rows


def _load_sql(source_spec: dict) -> list:
    """Run a read-only SELECT against the Colleague SQL Server and return rows."""
    query = source_spec.get('query')
    if not query or not str(query).strip():
        raise ValueError('source.query is required for mode "sql"')
    from services import sqlserver
    sqlserver.assert_read_only(query)
    max_rows = int(source_spec.get('max_rows') or sqlserver.DEFAULT_MAX_ROWS)
    return sqlserver.run_query(query, max_rows=max_rows)


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
