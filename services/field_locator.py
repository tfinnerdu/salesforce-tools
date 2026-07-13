"""Field Finder — given a field, find every object that has it.

The inverse of the Data Dictionary (object → its fields). Salesforce has no
plain-SOQL answer to "which objects have field X", so:

- **Fast path (custom fields):** one Tooling API ``CustomField`` query keyed on
  ``DeveloperName`` — the field's API name *without* the ``__c`` suffix or any
  namespace — resolving each hit's object via ``EntityDefinition.QualifiedApiName``.
- **Deep scan (opt-in, also finds standard fields):** DescribeGlobal, then
  describe each object and match the field by name. Exhaustive but hundreds of
  API calls, so it's capped and reported.

Input is normalized so a pasted ``SIS_ID__c`` or ``hed__SIS_ID__c`` resolves to
the same base name — the user never has to strip the ``__c`` themselves.
Read-only; nothing here writes to Salesforce.
"""
import logging

from services import cli_metadata
from sf_provider import get_sf
from utils.soql import escape_soql

logger = logging.getLogger(__name__)

# DescribeGlobal + a describe per object is O(objects) API calls; cap the deep
# scan so a big org can't hang the request, and report when we stopped short.
DEEP_SCAN_MAX_OBJECTS = 500


def normalize_field_name(field_name: str) -> str:
    """Reduce a field name to its ``CustomField.DeveloperName``.

    Strips a trailing ``__c`` and any managed-package namespace prefix, so all of
    ``SIS_ID__c`` / ``SIS_ID`` and ``hed__Foo__c`` / ``Foo`` collapse to the base
    name Salesforce stores in ``DeveloperName``. Standard names (``IsPersonAccount``)
    pass through unchanged.
    """
    name = (field_name or '').strip()
    base = name[:-3] if name.endswith('__c') else name
    # Managed-package prefix: <namespace>__<DeveloperName>. Split once — a custom
    # field's own DeveloperName never contains '__'.
    if '__' in base:
        base = base.split('__', 1)[1]
    return base


def _reconstruct_api_name(dev_name: str, namespace: str) -> str:
    """Rebuild a custom field's full API name from its parts."""
    return f'{namespace}__{dev_name}__c' if namespace else f'{dev_name}__c'


def _add(results: dict, obj: str, entry: dict) -> None:
    """Insert or enrich the row for an object (first source wins; later fills gaps)."""
    existing = results.get(obj)
    if existing is None:
        results[obj] = entry
        return
    for key in ('type', 'label', 'api_name'):
        if not existing.get(key) and entry.get(key):
            existing[key] = entry[key]


def _tooling_custom_fields(sf, base: str) -> list:
    """Tooling CustomField rows whose DeveloperName matches base (exact, case-insensitive)."""
    soql = ('SELECT DeveloperName, NamespacePrefix, MasterLabel, '
            'EntityDefinition.QualifiedApiName FROM CustomField '
            f"WHERE DeveloperName = '{escape_soql(base)}'")
    resp = sf.restful('tooling/query', params={'q': soql}) or {}
    rows = []
    for r in resp.get('records', []):
        dev = r.get('DeveloperName') or ''
        # The mock (and a LIKE query on real SF) can return extra rows; keep exact.
        if dev.lower() != base.lower():
            continue
        entity = r.get('EntityDefinition') or {}
        obj = entity.get('QualifiedApiName') or r.get('TableEnumOrId')
        if not obj:
            continue
        namespace = r.get('NamespacePrefix') or ''
        rows.append({
            'object': obj,
            'api_name': _reconstruct_api_name(dev, namespace),
            'label': r.get('MasterLabel') or r.get('Label') or '',
            'namespace': namespace,
            'type': '',
            'custom': True,
        })
    return rows


def _deep_scan(sf, base: str) -> tuple:
    """Describe every object and collect fields whose normalized name matches base.

    Returns (rows, scanned_count, truncated).
    """
    try:
        objects = cli_metadata.list_objects_from(sf)
    except Exception as exc:
        logger.warning('field_locator deep scan: object list failed: %s', exc)
        return [], 0, False

    names = [o['name'] for o in objects if o.get('name')]
    truncated = len(names) > DEEP_SCAN_MAX_OBJECTS
    names = names[:DEEP_SCAN_MAX_OBJECTS]

    rows, scanned = [], 0
    for obj in names:
        scanned += 1
        try:
            desc = cli_metadata.describe_fields_from(sf, obj)
        except Exception as exc:
            logger.debug('field_locator deep scan: describe %s failed: %s', obj, exc)
            continue
        for f in desc.get('fields', []):
            fname = f.get('name') or ''
            if normalize_field_name(fname).lower() == base.lower():
                rows.append({
                    'object': obj,
                    'api_name': fname,
                    'label': f.get('label') or '',
                    'namespace': '',
                    'type': f.get('type') or '',
                    'custom': bool(f.get('custom', fname.endswith('__c'))),
                })
    return rows, scanned, truncated


def find(org: str, field_name: str, include_standard: bool = False) -> dict:
    """Find every object carrying ``field_name``.

    Always runs the fast Tooling ``CustomField`` lookup (custom fields). When
    ``include_standard`` is set, also runs the describe sweep so standard fields
    (and custom fields the Tooling path missed) are found — slower.

    Returns ``{field, normalized, results, object_count, custom_matches,
    standard_matches, method, deep_scanned, truncated}`` with ``results`` a list
    of ``{object, api_name, label, namespace, type, custom}`` sorted by object.
    """
    sf = get_sf(org)
    base = normalize_field_name(field_name)
    empty = {
        'field': field_name, 'normalized': base, 'results': [], 'object_count': 0,
        'custom_matches': 0, 'standard_matches': 0, 'method': 'tooling',
        'deep_scanned': 0, 'truncated': False,
    }
    if not base:
        return empty

    results: dict = {}

    # Fast path: custom fields via Tooling.
    for row in _tooling_custom_fields(sf, base):
        _add(results, row['object'], row)
    custom_matches = len(results)

    method = 'tooling'
    deep_scanned = 0
    truncated = False
    if include_standard:
        method = 'describe'
        rows, deep_scanned, truncated = _deep_scan(sf, base)
        for row in rows:
            _add(results, row['object'], row)

    ordered = sorted(results.values(), key=lambda r: r['object'].lower())
    standard_matches = sum(1 for r in ordered if not r['custom'])
    return {
        'field': field_name,
        'normalized': base,
        'results': ordered,
        'object_count': len(ordered),
        'custom_matches': custom_matches,
        'standard_matches': standard_matches,
        'method': method,
        'deep_scanned': deep_scanned,
        'truncated': truncated,
    }
