"""Data Dictionary service — fetches full field metadata for a Salesforce object."""
import logging

from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)


def _mock_catalog(sobject: str) -> dict:
    """Return a mock field catalog for testing/dev without real SF credentials."""
    fields = [
        {
            'label': 'SIS ID',
            'api_name': 'SIS_ID__c',
            'type': 'string',
            'length': 18,
            'required': False,
            'unique': True,
            'external_id': True,
            'custom': True,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': 'Colleague person ID — used as external ID for upsert.',
            'description': 'Primary external identifier from the SIS (Colleague).',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
        {
            'label': 'Ethos GUID',
            'api_name': 'Ethos_Guid__c',
            'type': 'string',
            'length': 36,
            'required': False,
            'unique': True,
            'external_id': True,
            'custom': True,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': 'LDM GUID from Ethos Integration.',
            'description': 'Secondary external identifier from the Ethos data model.',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
        {
            'label': 'Email',
            'api_name': 'PersonEmail__pc',
            'type': 'email',
            'length': 80,
            'required': False,
            'unique': False,
            'external_id': False,
            'custom': True,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': '',
            'description': 'Person Account email field.',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
        {
            'label': 'Migration Status',
            'api_name': 'Migration_Status__c',
            'type': 'picklist',
            'length': '',
            'required': False,
            'unique': False,
            'external_id': False,
            'custom': True,
            'formula': '',
            'default_value': 'Pending',
            'picklist_values': 'Pending, In Progress, Complete, Error',
            'help_text': 'Current state of the EDA to Ed Cloud migration for this record.',
            'description': '',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
        {
            'label': 'Record ID',
            'api_name': 'Id',
            'type': 'id',
            'length': 18,
            'required': False,
            'unique': True,
            'external_id': False,
            'custom': False,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': '',
            'description': '',
            'createable': False,
            'updateable': False,
            'filterable': True,
        },
        {
            'label': 'Full Name',
            'api_name': 'Name',
            'type': 'string',
            'length': 121,
            'required': True,
            'unique': False,
            'external_id': False,
            'custom': False,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': '',
            'description': 'Full name derived from First + Last.',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
        {
            'label': 'Is Person Account',
            'api_name': 'IsPersonAccount',
            'type': 'boolean',
            'length': '',
            'required': False,
            'unique': False,
            'external_id': False,
            'custom': False,
            'formula': '',
            'default_value': 'False',
            'picklist_values': '',
            'help_text': '',
            'description': '',
            'createable': False,
            'updateable': False,
            'filterable': True,
        },
        {
            'label': 'Birthdate',
            'api_name': 'PersonBirthdate',
            'type': 'date',
            'length': '',
            'required': False,
            'unique': False,
            'external_id': False,
            'custom': False,
            'formula': '',
            'default_value': '',
            'picklist_values': '',
            'help_text': '',
            'description': '',
            'createable': True,
            'updateable': True,
            'filterable': True,
        },
    ]
    custom_count = sum(1 for f in fields if f['custom'])
    return {
        'sobject': sobject,
        'label': sobject,
        'field_count': len(fields),
        'custom_count': custom_count,
        'fields': fields,
    }


def get_field_catalog(org: str, sobject: str) -> dict:
    """Return full field metadata for a Salesforce object."""
    sf = get_sf(org)
    try:
        desc = sf.restful(f'sobjects/{sobject}/describe/')
    except Exception as exc:
        logger.warning('describe failed for %s: %s — using mock fallback', sobject, exc)
        if Config.SHOW_MOCK:
            return _mock_catalog(sobject)
        raise

    sobject_label = desc.get('label', sobject)
    raw_fields = desc.get('fields', [])

    if not raw_fields and Config.SHOW_MOCK:
        logger.info('describe returned no fields in mock mode — using mock fallback for %s', sobject)
        return _mock_catalog(sobject)

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
