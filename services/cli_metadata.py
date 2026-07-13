"""CLI tab — describe-driven metadata for the object / field pickers.

Read-only. Reuses the same REST describe path the Schema, SOQL, and Data
Dictionary tabs already use (`sf.restful('sobjects')` for the object list and
`sf.restful('sobjects/<obj>/describe')` for fields). Nothing here writes to
Salesforce.

Shaped as a small, reusable layer so the future in-app autocomplete command
composer (Phase 2) can consume the same object/field metadata without change.
Each public `*_from(sf, ...)` helper takes an injected client for testability;
the thin `list_objects` / `describe_fields` wrappers resolve the client via
`get_sf(org)`.
"""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def list_objects(org: str = 'dev') -> list:
    """Return the org's SObjects as [{name, label, custom, queryable}], A→Z."""
    return list_objects_from(get_sf(org))


def list_objects_from(sf) -> list:
    """Object list from an injected SF client (see list_objects).

    Each object carries the DescribeGlobal capability flags the shared object
    picker filters on, so one call to `/meta/objects` can be scoped per context
    (SOQL wants ``queryable``; the CLI field builder wants ``customizable`` —
    i.e. ``layoutable`` — so system objects like ContentDocumentLink / ContentNote
    that reject custom fields never appear where they'd only fail on deploy).
    ``layoutable`` is the reliable DescribeGlobal proxy for "can add custom
    fields": it's true for custom objects and standard objects with page
    layouts, and false for relationship/system objects (ContentDocumentLink,
    ContentNote, ``*__Share``, ``*__History`` …).
    """
    result = sf.restful('sobjects') or {}
    objs = [
        {
            'name': s.get('name'),
            'label': s.get('label') or s.get('name'),
            'custom': bool(s.get('custom', False)),
            'queryable': bool(s.get('queryable', True)),
            'layoutable': bool(s.get('layoutable', True)),
            'createable': bool(s.get('createable', True)),
            'updateable': bool(s.get('updateable', True)),
            'deletable': bool(s.get('deletable', True)),
        }
        for s in result.get('sobjects', [])
        if s.get('name')
    ]
    objs.sort(key=lambda o: o['name'].lower())
    return objs


def describe_fields(org: str, object_name: str) -> dict:
    """Return {object, label, custom, fields:[...]} for one object."""
    return describe_fields_from(get_sf(org), object_name)


def describe_fields_from(sf, object_name: str) -> dict:
    """Field describe from an injected SF client (see describe_fields).

    Each field carries exactly the attributes the CLI builder needs to
    prefill a create form or an External-ID *flip* (so a redeploy reproduces
    the field's current spec rather than clobbering it): type, length,
    precision/scale, externalId/idLookup/unique, and picklist values.
    """
    desc = sf.restful(f'sobjects/{object_name}/describe') or {}
    fields = [
        {
            'name': f.get('name'),
            'label': f.get('label') or f.get('name'),
            'type': f.get('type'),
            'length': f.get('length') or 0,
            'precision': f.get('precision') or 0,
            'scale': f.get('scale') or 0,
            'custom': bool(f.get('custom', False)),
            'externalId': bool(f.get('externalId', False)),
            'idLookup': bool(f.get('idLookup', False)),
            'unique': bool(f.get('unique', False)),
            'nillable': bool(f.get('nillable', True)),
            'picklistValues': [
                {
                    'value': pv.get('value'),
                    'label': pv.get('label') or pv.get('value'),
                    'active': bool(pv.get('active', True)),
                }
                for pv in f.get('picklistValues', [])
            ],
        }
        for f in desc.get('fields', [])
        if f.get('name')
    ]
    fields.sort(key=lambda x: x['name'].lower())
    return {
        'object': object_name,
        'label': desc.get('label') or object_name,
        'custom': bool(desc.get('custom', False)),
        'fields': fields,
    }
