"""Data Dictionary service — fetches full field metadata for a Salesforce object."""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def get_field_catalog(org: str, sobject: str) -> dict:
    """Return full field metadata for a Salesforce object."""
    sf = get_sf(org)
    try:
        desc = sf.restful(f'sobjects/{sobject}/describe/')
    except Exception as exc:
        logger.warning('describe failed for %s: %s', sobject, exc)
        raise

    sobject_label = desc.get('label', sobject)
    raw_fields = desc.get('fields', [])

    fields = []
    for f in raw_fields:
        picklist_vals = ', '.join(
            pv.get('value', '')
            for pv in f.get('picklistValues', [])
            if pv.get('active', True)
        )
        fields.append({
            'label':          f.get('label', ''),
            'api_name':       f.get('name', ''),
            'type':           f.get('type', ''),
            'length':         f.get('length') or f.get('precision') or '',
            'required':       not f.get('nillable', True) and not f.get('defaultedOnCreate', False),
            'unique':         f.get('unique', False),
            'external_id':    f.get('externalId', False),
            'custom':         f.get('name', '').endswith('__c'),
            'formula':        f.get('calculatedFormula') or '',
            'default_value':  str(f.get('defaultValue', '')) if f.get('defaultValue') is not None else '',
            'picklist_values': picklist_vals,
            'help_text':      f.get('inlineHelpText') or '',
            'description':    f.get('description') or '',
            'createable':     f.get('createable', False),
            'updateable':     f.get('updateable', False),
            'filterable':     f.get('filterable', False),
        })

    # Sort: custom fields first, then standard, alphabetical within each group
    fields.sort(key=lambda x: (not x['custom'], x['api_name'].lower()))

    return {
        'sobject': sobject,
        'label': sobject_label,
        'field_count': len(fields),
        'custom_count': sum(1 for f in fields if f['custom']),
        'fields': fields,
    }
