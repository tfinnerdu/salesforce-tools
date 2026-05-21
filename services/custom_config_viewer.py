import logging
from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)


def get_custom_metadata_types(org: str) -> list:
    """List all Custom Metadata Types via Tooling API."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        return _mock_cmdts()
    try:
        resp = sf.restful('tooling/query/', params={'q': "SELECT Id, DeveloperName, Label, Description FROM CustomObject WHERE ManageableState='unmanaged' AND DeveloperName LIKE '%mdt%'"})
        records = resp.get('records', [])
        if not records:
            # fallback: EntityDefinition approach
            resp2 = sf.restful('tooling/query/', params={'q': "SELECT QualifiedApiName, Label, InternalSharingModel FROM EntityDefinition WHERE IsCustomizable=true AND QualifiedApiName LIKE '%__mdt' LIMIT 50"})
            records = resp2.get('records', [])
        return records
    except Exception as exc:
        logger.warning('custom metadata types failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_cmdts()
        raise


def get_custom_metadata_records(org: str, type_name: str) -> list:
    """List all records of a Custom Metadata Type."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        return _mock_cmdt_records(type_name)
    try:
        soql = f'SELECT Id, DeveloperName, Label, MasterLabel FROM {type_name} LIMIT 200'
        result = sf.query(soql)
        return result.get('records', [])
    except Exception as exc:
        logger.warning('custom metadata records failed for %s: %s', type_name, exc)
        if Config.SF_MOCK:
            return _mock_cmdt_records(type_name)
        raise


def get_custom_settings(org: str) -> list:
    """List Custom Settings objects and their record counts."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        return _mock_custom_settings()
    try:
        resp = sf.restful('tooling/query/', params={'q': "SELECT QualifiedApiName, Label, InternalSharingModel FROM EntityDefinition WHERE IsCustomizable=true AND QualifiedApiName LIKE '%__c' LIMIT 100"})
        records = resp.get('records', [])
        return records
    except Exception as exc:
        logger.warning('custom settings list failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_custom_settings()
        raise


def get_custom_setting_records(org: str, setting_name: str) -> list:
    """List all records for a Hierarchy or List custom setting."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        return _mock_setting_records(setting_name)
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
        if Config.SF_MOCK:
            return _mock_setting_records(setting_name)
        raise


def _mock_cmdts() -> list:
    return [
        {'QualifiedApiName': 'Integration_Setting__mdt', 'Label': 'Integration Setting', 'InternalSharingModel': 'ReadWrite'},
        {'QualifiedApiName': 'Field_Mapping__mdt', 'Label': 'Field Mapping', 'InternalSharingModel': 'ReadWrite'},
        {'QualifiedApiName': 'Migration_Config__mdt', 'Label': 'Migration Config', 'InternalSharingModel': 'ReadWrite'},
    ]


def _mock_cmdt_records(type_name: str) -> list:
    return [
        {'Id': 'mCR001', 'DeveloperName': 'Default', 'Label': 'Default', 'MasterLabel': 'Default'},
        {'Id': 'mCR002', 'DeveloperName': 'Ethos_Config', 'Label': 'Ethos Config', 'MasterLabel': 'Ethos Config'},
    ]


def _mock_custom_settings() -> list:
    return [
        {'QualifiedApiName': 'Integration_Config__c', 'Label': 'Integration Config', 'InternalSharingModel': 'ReadWrite'},
        {'QualifiedApiName': 'Migration_Flags__c', 'Label': 'Migration Flags', 'InternalSharingModel': 'Protected'},
    ]


def _mock_setting_records(setting_name: str) -> list:
    return [
        {'Id': 'SR001', 'Name': 'Org Default', 'SetupOwnerId': '00D000000000001', '_owner_type': 'Org'},
        {'Id': 'SR002', 'Name': 'Admin Override', 'SetupOwnerId': '00e000000000001', '_owner_type': 'Profile'},
    ]
