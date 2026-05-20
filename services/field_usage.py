"""Field Usage — data completeness heatmap for a Salesforce object.

For each field, runs SELECT COUNT() FROM {Object} WHERE {field} != null and
divides by total record count to compute a fill percentage.
"""
import logging

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

ALWAYS_INCLUDE = {
    'Id', 'Name', 'CreatedDate', 'LastModifiedDate', 'OwnerId',
    'IsPersonAccount', 'SIS_ID__c', 'Ethos_Guid__c', 'PersonEmail',
}

MAX_FIELDS = 40


def get_field_list(org: str, sobject: str) -> list:
    """Return field metadata for an SF object (name, label, type, custom)."""
    sf = get_sf(org)
    desc = sf.restful(f'sobjects/{sobject}/describe/')
    fields = desc.get('fields', [])
    return [
        {
            'name': f['name'],
            'label': f['label'],
            'type': f['type'],
            'custom': f['name'].endswith('__c'),
        }
        for f in fields
        if f.get('queryable', True)
    ]


def _status(pct) -> str:
    if pct is None:
        return 'skip'
    if pct == 0.0:
        return 'empty'
    if pct < 25:
        return 'red'
    if pct < 75:
        return 'amber'
    return 'green'


def _mock_result(sobject: str) -> dict:
    total = 4312
    return {
        'sobject': sobject,
        'total_records': total,
        'fields': [
            {'name': 'SIS_ID__c',       'label': 'SIS ID',        'type': 'string', 'custom': True,  'total': total, 'populated': 4289, 'pct': 99.5, 'status': 'green'},
            {'name': 'Ethos_Guid__c',   'label': 'Ethos GUID',    'type': 'string', 'custom': True,  'total': total, 'populated': 4100, 'pct': 95.1, 'status': 'green'},
            {'name': 'PersonEmail',     'label': 'Email',          'type': 'email',  'custom': False, 'total': total, 'populated': 3980, 'pct': 92.3, 'status': 'green'},
            {'name': 'PersonBirthdate', 'label': 'Birthdate',      'type': 'date',   'custom': False, 'total': total, 'populated': 2100, 'pct': 48.7, 'status': 'amber'},
            {'name': 'Phone',           'label': 'Phone',          'type': 'phone',  'custom': False, 'total': total, 'populated': 890,  'pct': 20.6, 'status': 'red'},
            {'name': 'BillingStreet',   'label': 'Billing Street', 'type': 'string', 'custom': False, 'total': total, 'populated': 0,    'pct': 0.0,  'status': 'empty'},
        ],
    }


def run(org: str, sobject: str, fields: list = None) -> dict:
    """For each field, count total records and records where field != null.

    Returns {sobject, total_records, fields: list of
    {name, label, type, custom, total, populated, pct, status}}
    """
    sf = get_sf(org)

    # ── Determine field list ─────────────────────────────────────────────────
    if not fields:
        all_fields = get_field_list(org, sobject)
        custom_fields = [f for f in all_fields if f['custom']]
        standard_fields = [f for f in all_fields if not f['custom'] and f['name'] in ALWAYS_INCLUDE]

        # Custom first, then key standard fields, cap at MAX_FIELDS
        chosen = custom_fields[:MAX_FIELDS]
        remaining = MAX_FIELDS - len(chosen)
        chosen += standard_fields[:remaining]
        field_meta = chosen
    else:
        # Caller supplied explicit list of field names — build minimal metadata
        all_fields = get_field_list(org, sobject)
        meta_by_name = {f['name']: f for f in all_fields}
        field_meta = [
            meta_by_name.get(fn, {'name': fn, 'label': fn, 'type': 'unknown', 'custom': fn.endswith('__c')})
            for fn in fields
        ]

    # ── Total record count ────────────────────────────────────────────────────
    try:
        total_result = sf.query(f'SELECT COUNT() FROM {sobject}')
        total = total_result.get('totalSize', 0)
    except Exception as exc:
        logger.warning('field_usage: total count failed for %s: %s', sobject, exc)
        if Config.SF_MOCK:
            return _mock_result(sobject)
        raise

    if Config.SF_MOCK and total == 0:
        return _mock_result(sobject)

    # ── Per-field null check ──────────────────────────────────────────────────
    results = []
    for fmeta in field_meta:
        fname = fmeta['name']
        try:
            r = sf.query(f'SELECT COUNT() FROM {sobject} WHERE {fname} != null')
            populated = r.get('totalSize', 0)
            pct = round((populated / total) * 100, 1) if total > 0 else 0.0
            status = _status(pct)
        except Exception as exc:
            logger.debug('field_usage: field %s not filterable on %s: %s', fname, sobject, exc)
            populated = None
            pct = None
            status = 'skip'

        results.append({
            'name': fname,
            'label': fmeta['label'],
            'type': fmeta['type'],
            'custom': fmeta['custom'],
            'total': total,
            'populated': populated,
            'pct': pct,
            'status': status,
        })

    # Sort emptiest first (None/skip goes to end)
    results.sort(key=lambda r: (r['pct'] is None, r['pct'] if r['pct'] is not None else 0))

    return {
        'sobject': sobject,
        'total_records': total,
        'fields': results,
    }
