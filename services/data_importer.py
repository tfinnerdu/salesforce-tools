"""Data Import — CSV → Salesforce via Bulk API with per-record error reporting."""
import csv
import io
import logging
from typing import Any

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_MAX_ROWS = 50_000
_PICKLIST_CACHE: dict = {}


# ── Schema helpers ────────────────────────────────────────────────────────────

def get_object_fields(org: str, object_name: str) -> list:
    """Return field metadata for an object (name, label, type, required, picklist values)."""
    sf = get_sf(org)
    try:
        desc = sf.restful(f'sobjects/{object_name}/describe')
    except Exception as exc:
        raise ValueError(f"Could not describe '{object_name}': {exc}") from exc

    fields = []
    for f in desc.get('fields', []):
        picklist_vals = None
        if f.get('type') in ('picklist', 'multipicklist'):
            picklist_vals = [pv['value'] for pv in f.get('picklistValues', []) if pv.get('active')]
        fields.append({
            'name': f['name'],
            'label': f.get('label', f['name']),
            'type': f.get('type', 'string'),
            'required': bool(f.get('nillable') is False and not f.get('defaultedOnCreate') and f.get('createable')),
            'createable': bool(f.get('createable', False)),
            'updateable': bool(f.get('updateable', False)),
            'external_id': bool(f.get('externalId', False)),
            'unique': bool(f.get('unique', False)),
            'picklist_values': picklist_vals,
            'reference_to': f.get('referenceTo', []),
        })
    return fields


# ── Validation ────────────────────────────────────────────────────────────────

def validate_csv(org: str, object_name: str, csv_text: str, field_mapping: dict,
                 operation: str = 'insert') -> dict:
    """
    Validate CSV rows against SF schema without writing anything.

    field_mapping: {csv_col: sf_field_name}
    operation: insert | update | upsert | delete

    Returns {
        total_rows, clean_rows, warning_rows, error_rows,
        errors: [{row, field, message, severity}],
        summary: {field: {issues: int}}
    }
    """
    sf_fields = {f['name'].lower(): f for f in get_object_fields(org, object_name)}
    mapped_fields = {csv_col: sf_fields.get(sf_field.lower()) for csv_col, sf_field in field_mapping.items()}

    rows = _parse_csv(csv_text)
    if not rows:
        return {'total_rows': 0, 'clean_rows': 0, 'warning_rows': 0, 'error_rows': 0,
                'errors': [], 'summary': {}}

    errors = []
    row_flags: dict = {}  # row_num → 'error' | 'warning'

    for i, row in enumerate(rows):
        row_num = i + 1
        for csv_col, sf_field_meta in mapped_fields.items():
            if sf_field_meta is None:
                errors.append({'row': row_num, 'field': csv_col, 'severity': 'error',
                                'message': f"Column '{csv_col}' maps to an unknown SF field"})
                row_flags[row_num] = 'error'
                continue

            value = row.get(csv_col, '')
            sf_name = sf_field_meta['name']
            ftype = sf_field_meta['type']

            # Required field check (insert only)
            if operation == 'insert' and sf_field_meta.get('required') and not value:
                errors.append({'row': row_num, 'field': sf_name, 'severity': 'error',
                                'message': f"Required field '{sf_name}' is empty"})
                row_flags[row_num] = 'error'
                continue

            if not value:
                continue

            # Type checks
            if ftype in ('int', 'integer'):
                try:
                    int(value)
                except ValueError:
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'error',
                                    'message': f"'{value}' is not a valid integer for field '{sf_name}'"})
                    row_flags[row_num] = 'error'

            elif ftype in ('double', 'currency', 'percent'):
                try:
                    float(value)
                except ValueError:
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'error',
                                    'message': f"'{value}' is not a valid number for field '{sf_name}'"})
                    row_flags[row_num] = 'error'

            elif ftype in ('date',):
                import re
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'warning',
                                    'message': f"'{value}' may not be a valid date (expected YYYY-MM-DD) for '{sf_name}'"})
                    if row_num not in row_flags:
                        row_flags[row_num] = 'warning'

            elif ftype in ('datetime',):
                import re
                if not re.match(r'^\d{4}-\d{2}-\d{2}', value):
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'warning',
                                    'message': f"'{value}' may not be a valid datetime for '{sf_name}'"})
                    if row_num not in row_flags:
                        row_flags[row_num] = 'warning'

            elif ftype in ('boolean',):
                if value.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'warning',
                                    'message': f"'{value}' is not a clear boolean for '{sf_name}' (use true/false)"})
                    if row_num not in row_flags:
                        row_flags[row_num] = 'warning'

            elif ftype in ('email',):
                import re
                if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value):
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'error',
                                    'message': f"'{value}' is not a valid email address for '{sf_name}'"})
                    row_flags[row_num] = 'error'

            elif ftype in ('picklist',):
                allowed = sf_field_meta.get('picklist_values') or []
                if allowed and value not in allowed:
                    errors.append({'row': row_num, 'field': sf_name, 'severity': 'error',
                                    'message': f"'{value}' is not a valid picklist value for '{sf_name}'. Allowed: {', '.join(allowed[:5])}{'…' if len(allowed) > 5 else ''}"})
                    row_flags[row_num] = 'error'

    total = len(rows)
    error_count = sum(1 for v in row_flags.values() if v == 'error')
    warning_count = sum(1 for v in row_flags.values() if v == 'warning')
    clean = total - error_count - warning_count

    # Summarize by field
    summary: dict = {}
    for e in errors:
        f = e['field']
        if f not in summary:
            summary[f] = {'errors': 0, 'warnings': 0}
        summary[f][e['severity'] + 's'] += 1

    return {
        'total_rows': total,
        'clean_rows': clean,
        'warning_rows': warning_count,
        'error_rows': error_count,
        'errors': errors[:500],  # cap for response size
        'summary': summary,
        'object_name': object_name,
        'operation': operation,
    }


# ── Import ────────────────────────────────────────────────────────────────────

def import_csv(org: str, object_name: str, csv_text: str, field_mapping: dict,
               operation: str = 'insert', external_id_field: str = '',
               bypass_triggers: bool = False) -> dict:
    """
    Import CSV rows into Salesforce via the Bulk API 2.0.

    Returns {
        success_count, error_count, total,
        results: [{row, sf_id, success, errors}],   # failed rows only
        error_csv: str  (the Bulk API failed-records CSV: sf__Id, sf__Error, …)
    }
    """
    sf = get_sf(org)
    rows = _parse_csv(csv_text)
    if not rows:
        return {'success_count': 0, 'error_count': 0, 'total': 0, 'results': [], 'error_csv': ''}

    if len(rows) > _MAX_ROWS:
        raise ValueError(f"CSV has {len(rows):,} rows — maximum is {_MAX_ROWS:,} per operation")

    if operation.lower() == 'upsert' and not external_id_field:
        raise ValueError('external_id_field is required for upsert')

    # Build SF record dicts from the column mapping.
    sf_records = []
    for row in rows:
        rec: dict = {}
        for csv_col, sf_field in field_mapping.items():
            val = row.get(csv_col, '')
            rec[sf_field] = val if val != '' else None
        sf_records.append(rec)

    from sf_provider import bulk2_dml, bulk2_failed_records, set_bypass_triggers
    if bypass_triggers:
        set_bypass_triggers(sf, True)
    try:
        res = bulk2_dml(sf, object_name, operation, sf_records, external_id_field)
        error_csv = bulk2_failed_records(sf, object_name, res['job_ids']) if res['failed'] else ''
    finally:
        if bypass_triggers:
            set_bypass_triggers(sf, False)

    # Bulk API 2.0 reports per-record detail only for failures (sf__Id, sf__Error,
    # plus the original request fields). Successes are not itemised.
    results = []
    if error_csv:
        reader = csv.DictReader(io.StringIO(error_csv))
        for i, frow in enumerate(reader):
            results.append({
                'row': i + 1,
                'sf_id': frow.get('sf__Id', '') or '',
                'success': False,
                'errors': frow.get('sf__Error', '') or '',
                'source': {k: v for k, v in frow.items()
                           if k not in ('sf__Id', 'sf__Error')},
            })

    return {
        'success_count': res['succeeded'],
        'error_count': res['failed'],
        'total': res['total'] or len(rows),
        'results': results[:1000],  # cap for response size
        'error_csv': error_csv,
        'object_name': object_name,
        'operation': operation,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_csv(csv_text: str) -> list:
    if not csv_text:
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    return [dict(row) for row in reader]
