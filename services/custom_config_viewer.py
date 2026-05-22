import logging
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def get_custom_metadata_types(org: str) -> list:
    """List Custom Metadata Types via the EntityDefinition Tooling object.

    The Tooling CustomObject entity has no queryable Label/Description columns
    (they live inside Metadata). EntityDefinition exposes Label directly and
    reliably enumerates __mdt types; it requires a LIMIT (no queryMore).
    """
    sf = get_sf(org)
    try:
        resp = sf.restful('tooling/query/', params={'q': (
            "SELECT QualifiedApiName, Label FROM EntityDefinition "
            "WHERE QualifiedApiName LIKE '%__mdt' ORDER BY Label LIMIT 500"
        )})
        return resp.get('records', [])
    except Exception as exc:
        logger.warning('custom metadata types failed: %s', exc)
        raise


def get_custom_metadata_records(org: str, type_name: str) -> list:
    """List all records of a Custom Metadata Type."""
    sf = get_sf(org)
    try:
        soql = f'SELECT Id, DeveloperName, Label, MasterLabel FROM {type_name} LIMIT 200'
        result = sf.query(soql)
        return result.get('records', [])
    except Exception as exc:
        logger.warning('custom metadata records failed for %s: %s', type_name, exc)
        raise


def get_custom_settings(org: str) -> list:
    """List Custom Settings objects and their record counts."""
    sf = get_sf(org)
    try:
        resp = sf.restful('tooling/query/', params={'q': "SELECT QualifiedApiName, Label, InternalSharingModel FROM EntityDefinition WHERE IsCustomizable=true AND QualifiedApiName LIKE '%__c' LIMIT 100"})
        records = resp.get('records', [])
        return records
    except Exception as exc:
        logger.warning('custom settings list failed: %s', exc)
        raise


def get_custom_setting_records(org: str, setting_name: str) -> list:
    """List all records for a Hierarchy or List custom setting."""
    sf = get_sf(org)
    try:
        soql = f'SELECT Id, Name, SetupOwnerId FROM {setting_name} LIMIT 100'
        result = sf.query(soql)
        records = result.get('records', [])
        # Add SetupOwner type hint
        for r in records:
            owner_id = r.get('SetupOwnerId', '')
            r['_owner_type'] = 'Org' if owner_id.startswith('00D') else ('Profile' if owner_id.startswith('00e') else 'User')
        return records
    except Exception as exc:
        logger.warning('custom setting records failed for %s: %s', setting_name, exc)
        raise
