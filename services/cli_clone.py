"""CLI tab — clone a whole object's schema into a deployable metadata package.

Given a *source* object, describe it and turn each custom field into the same
field spec the CLI field builder uses, so the existing generators
(``cli_script.field_meta_xml`` / ``build_package_zip``) produce a ``force-app``
package the admin deploys to the target org. A best-effort ``CustomObject`` shell
can ride along to create the object if it doesn't exist yet.

Deploy is inherently upsert (create if missing, update if present), so no record
identity handling is needed. Fields the generator can't reproduce 1:1 —
relationships (lookup/master-detail), formula / roll-up, auto-number, and
unsupported types (currency, percent, multipicklist, rich text, …) — are
**skipped and reported**, never silently dropped.

Read-only against Salesforce; the mapping helpers are pure over an injected
describe payload.
"""
import logging

from services import cli_script
from sf_provider import get_sf

logger = logging.getLogger(__name__)

# Salesforce describe field-type → CLI metadata field-type. 'textarea' is
# resolved by length/rich-text at map time (Text Area vs Long Text Area vs the
# unsupported rich-text), so it isn't a simple 1:1 here.
_TYPE_MAP = {
    'string': 'Text',
    'boolean': 'Checkbox',
    'double': 'Number',
    'int': 'Number',
    'date': 'Date',
    'datetime': 'DateTime',
    'email': 'Email',
    'phone': 'Phone',
    'url': 'Url',
    'picklist': 'Picklist',
}

# describe types the field builder can't reproduce — reported with this reason.
_UNSUPPORTED_REASON = {
    'reference': 'relationship (lookup / master-detail)',
    'currency': 'currency field (unsupported type)',
    'percent': 'percent field (unsupported type)',
    'multipicklist': 'multi-select picklist (unsupported type)',
    'time': 'time field (unsupported type)',
    'location': 'geolocation field (unsupported type)',
    'address': 'compound address field (unsupported type)',
    'base64': 'binary field (unsupported type)',
    'encryptedstring': 'encrypted text (unsupported type)',
    'anyType': 'anyType field (unsupported type)',
    'combobox': 'combobox field (unsupported type)',
    'datacategorygroupreference': 'data-category reference (unsupported type)',
}


def _field_spec(f: dict, object_name: str):
    """Map one describe field → (spec, None) or (None, reason).

    Only custom fields are cloned; standard fields return (None, None) — they're
    counted, not itemized. A returned ``reason`` marks a custom field the builder
    can't reproduce (relationship / formula / auto-number / unsupported type).
    """
    name = f.get('name') or ''
    if not name.endswith('__c'):
        return None, None                     # standard field — belongs to the shell

    if f.get('autoNumber'):
        return None, 'auto-number field'
    if f.get('calculated'):                   # formula OR roll-up summary
        return None, 'formula / roll-up field'

    dtype = f.get('type') or ''
    if dtype in _UNSUPPORTED_REASON:
        return None, _UNSUPPORTED_REASON[dtype]

    if dtype == 'textarea':
        if f.get('htmlFormatted'):
            return None, 'rich text area (unsupported type)'
        mtype = 'LongTextArea' if (f.get('length') or 0) > 255 else 'TextArea'
    else:
        mtype = _TYPE_MAP.get(dtype)
    if not mtype:
        return None, f'{dtype or "unknown"} field (unsupported type)'

    spec = {'object': object_name, 'api_name': name,
            'label': f.get('label') or name, 'type': mtype}

    if mtype in cli_script._REQUIRED_TYPES:
        spec['required'] = not f.get('nillable', True)
    if mtype in ('Text', 'TextArea', 'LongTextArea'):
        spec['length'] = f.get('length') or (32768 if mtype == 'LongTextArea' else 255)
    if mtype == 'Number':
        spec['precision'] = f.get('precision') or 18
        spec['scale'] = f.get('scale') or 0
    if mtype in cli_script._EXTID_TYPES:
        spec['externalId'] = bool(f.get('externalId'))
        spec['unique'] = bool(f.get('unique'))
    if mtype == 'Text' and f.get('unique'):
        spec['caseSensitive'] = bool(f.get('caseSensitive'))
    if mtype == 'Checkbox':
        spec['defaultValue'] = bool(f.get('defaultValue'))
    if mtype == 'LongTextArea':
        spec['visibleLines'] = f.get('visibleLines') or 3
    if mtype == 'Picklist':
        spec['picklist'] = {
            'restricted': bool(f.get('restrictedPicklist')),
            'sorted': False,
            'values': [
                {'value': pv.get('value'), 'label': pv.get('label') or pv.get('value'),
                 'default': bool(pv.get('defaultValue')), 'active': bool(pv.get('active', True))}
                for pv in f.get('picklistValues', []) if pv.get('value')
            ],
        }
    return spec, None


def object_shell(desc: dict, object_name: str) -> dict:
    """Best-effort CustomObject shell spec from a describe payload.

    describe omits sharingModel and an auto-number name field's displayFormat, so
    those are defaulted (sharingModel=ReadWrite, a Text name field) and flagged in
    ``notes`` — the admin reviews before deploying to a brand-new object.
    """
    name_field = next((f for f in desc.get('fields', []) if f.get('nameField')), None)
    notes = ['sharingModel defaulted to ReadWrite (not exposed by describe)']
    name_label = (name_field or {}).get('label') or 'Name'
    if name_field and name_field.get('autoNumber'):
        notes.append(f'source name field "{name_label}" is Auto Number; emitted as Text '
                     '(set the display format after deploy)')
    return {
        'object': object_name,
        'label': desc.get('label') or object_name,
        'plural_label': desc.get('labelPlural') or desc.get('label') or object_name,
        'name_label': name_label,
        'sharing_model': 'ReadWrite',
        'notes': notes,
    }


def plan_from_object(org: str, object_name: str, include_shell: bool = False) -> dict:
    """Describe a source object and build a clone plan.

    Returns ``{object, is_custom, fields, skipped, shell, counts}`` where
    ``fields`` are ready-to-package CLI field specs, ``skipped`` is
    ``[{api_name, type, reason}]`` for custom fields that can't be reproduced,
    and ``shell`` is the CustomObject spec (or None).
    """
    object_name = (object_name or '').strip()
    if not object_name:
        raise ValueError('object is required')
    sf = get_sf(org)
    desc = sf.restful(f'sobjects/{object_name}/describe') or {}
    raw_fields = desc.get('fields', [])

    fields, skipped, standard = [], [], 0
    for f in raw_fields:
        spec, reason = _field_spec(f, object_name)
        if spec:
            fields.append(spec)
        elif reason:
            skipped.append({'api_name': f.get('name') or '',
                            'type': f.get('type') or '', 'reason': reason})
        else:
            standard += 1

    fields.sort(key=lambda s: s['api_name'].lower())
    skipped.sort(key=lambda s: s['api_name'].lower())

    is_custom = bool(desc.get('custom')) or object_name.endswith('__c')
    shell = object_shell(desc, object_name) if (include_shell and is_custom) else None

    return {
        'object': object_name,
        'label': desc.get('label') or object_name,
        'is_custom': is_custom,
        'fields': fields,
        'skipped': skipped,
        'shell': shell,
        'counts': {
            'custom_fields': len(fields),
            'skipped': len(skipped),
            'standard_fields': standard,
            'total_fields': len(raw_fields),
        },
    }
