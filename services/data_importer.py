"""Data Import — CSV → Salesforce via Bulk API with per-record error reporting."""
import csv
import io
import logging
from typing import Any

from config import Config
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
    Import CSV rows into Salesforce via Bulk API.

    Returns {
        success_count, error_count, total,
        results: [{row, id, success, errors}],
        error_csv: str  (CSV of failed rows with SF error column)
    }
    """
    if Config.SF_MOCK:
        return _mock_import_result(len(_parse_csv(csv_text)), operation)

    sf = get_sf(org)
    rows = _parse_csv(csv_text)
    if not rows:
        return {'success_count': 0, 'error_count': 0, 'total': 0, 'results': [], 'error_csv': ''}

    if len(rows) > _MAX_ROWS:
        raise ValueError(f"CSV has {len(rows):,} rows — maximum is {_MAX_ROWS:,} per operation")

    # Build SF record dicts from mapping
    sf_records = []
    for row in rows:
        rec: dict = {}
        for csv_col, sf_field in field_mapping.items():
            val = row.get(csv_col, '')
            rec[sf_field] = val if val != '' else None
        sf_records.append(rec)

    if bypass_triggers:
        from sf_provider import set_bypass_triggers
        set_bypass_triggers(sf, True)

    try:
        bulk_obj = getattr(sf.bulk, object_name)
        op = operation.lower()
        if op == 'insert':
            api_results = bulk_obj.insert(sf_records, batch_size=200, use_serial=False)
        elif op == 'update':
            api_results = bulk_obj.update(sf_records, batch_size=200, use_serial=False)
        elif op == 'upsert':
            if not external_id_field:
                raise ValueError('external_id_field is required for upsert')
            api_results = bulk_obj.upsert(sf_records, external_id_field, batch_size=200, use_serial=False)
        elif op == 'delete':
            api_results = bulk_obj.delete(sf_records, batch_size=200, use_serial=False)
        else:
            raise ValueError(f"Unknown operation '{operation}'")
    finally:
        if bypass_triggers:
            set_bypass_triggers(sf, False)

    # Process results
    results = []
    success_count = 0
    error_count = 0
    for i, (row, result) in enumerate(zip(rows, api_results or [])):
        if isinstance(result, dict):
            ok = bool(result.get('success'))
            row_errors = result.get('errors', [])
            err_msgs = '; '.join(
                f"{e.get('statusCode', '')}: {e.get('message', '')}" if isinstance(e, dict) else str(e)
                for e in (row_errors or [])
            )
        else:
            ok = False
            err_msgs = str(result)

        if ok:
            success_count += 1
        else:
            error_count += 1

        results.append({
            'row': i + 1,
            'id': result.get('id', '') if isinstance(result, dict) else '',
            'success': ok,
            'sf_id': result.get('id', '') if isinstance(result, dict) else '',
            'errors': err_msgs,
            'source': row,
        })

    # Build error CSV
    error_csv = ''
    failed_rows = [r for r in results if not r['success']]
    if failed_rows:
        original_cols = list(rows[0].keys()) if rows else []
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=original_cols + ['_sf_error'])
        writer.writeheader()
        for r in failed_rows:
            out_row = dict(r['source'])
            out_row['_sf_error'] = r['errors']
            writer.writerow(out_row)
        error_csv = buf.getvalue()

    return {
        'success_count': success_count,
        'error_count': error_count,
        'total': len(rows),
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


def _mock_import_result(row_count: int, operation: str) -> dict:
    total = max(row_count, 3)
    failed = max(1, total // 10)
    succeeded = total - failed
    results = []
    for i in range(total):
        ok = i < succeeded
        results.append({
            'row': i + 1,
            'sf_id': f'001MOCK{i:06d}' if ok else '',
            'success': ok,
            'errors': '' if ok else 'MOCK: Required field missing: SIS_ID__c',
        })
    return {
        'success_count': succeeded,
        'error_count': failed,
        'total': total,
        'results': results,
        'error_csv': '',
        'object_name': 'Account',
        'operation': operation,
        'mock': True,
    }
