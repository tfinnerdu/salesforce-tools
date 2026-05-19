"""Salesforce provider — returns real simple_salesforce client or a mock."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

from config import Config, get_org_config

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _configured(org: str) -> bool:
    """Return True when real SF credentials are present for this org."""
    cfg = get_org_config(org)
    return bool(cfg['username'] and cfg['password'])


def _parse_mock_count(soql: str) -> int:
    """Best-effort count extraction from a COUNT() SOQL query."""
    soql_lower = soql.lower()
    # Distinguish != null (covered) from = null (missing)
    missing_null = ('= null' in soql_lower or '=null' in soql_lower) and '!=' not in soql_lower.split('null')[0][-3:]
    covered_notnull = '!= null' in soql_lower or '!=null' in soql_lower

    if 'contactpointaddress' in soql_lower:
        if 'parentid' in soql_lower and missing_null:
            return 3204   # broken parent links
        if 'individualid' in soql_lower and missing_null:
            return 2800
        if 'sis_id__c' in soql_lower and missing_null:
            return 640
        if 'sis_id__c' in soql_lower and covered_notnull:
            return 3204 - 640
        return 3204
    if 'contactpointemail' in soql_lower:
        if 'parentid' in soql_lower and missing_null:
            return 683
        if 'individualid' in soql_lower and missing_null:
            return 512
        if 'sis_id__c' in soql_lower and missing_null:
            return 820
        if 'sis_id__c' in soql_lower and covered_notnull:
            return 4100 - 820
        return 4100
    if 'contactpointphone' in soql_lower:
        if 'parentid' in soql_lower and missing_null:
            return 633
        if 'individualid' in soql_lower and missing_null:
            return 422
        if 'sis_id__c' in soql_lower and missing_null:
            return 760
        if 'sis_id__c' in soql_lower and covered_notnull:
            return 3800 - 760
        return 3800
    if 'individualalplication' in soql_lower or 'individualapplication' in soql_lower:
        if 'sis_id__c' in soql_lower and missing_null:
            return 185
        if 'sis_id__c' in soql_lower and covered_notnull:
            return 1850 - 185
        if 'ethos_guid__c' in soql_lower and missing_null:
            return 200
        if 'ethos_guid__c' in soql_lower and covered_notnull:
            return 1850 - 200
        return 1850
    # PersonAccount variants
    if 'ispersonaccount' in soql_lower or 'personaccount' in soql_lower or 'account' in soql_lower:
        if 'sis_id__c' in soql_lower and missing_null:
            return 4312 - 3065  # 1247 missing SIS_ID
        if 'sis_id__c' in soql_lower and covered_notnull:
            return 3065
        if 'ethos_guid__c' in soql_lower and missing_null:
            return 4312 - 3923  # 389 missing Ethos_Guid
        if 'ethos_guid__c' in soql_lower and covered_notnull:
            return 3923
        if 'individualid' in soql_lower and missing_null:
            return 0  # Individual links: all good (mock)
        if 'firstname' in soql_lower and missing_null:
            return 44
        if 'lastname' in soql_lower and missing_null:
            return 12
        if 'recordtypeid' in soql_lower and missing_null:
            return 3
        return 4312
    return 100


def _make_person_account(idx: int) -> dict:
    return {
        # TODO(salesforce): confirm PersonAccount field API names against org schema
        'Id': f'001{idx:015d}',
        'Name': f'Test Student {idx}',
        'IsPersonAccount': True,
        'SIS_ID__c': f'STU{idx:05d}' if idx % 4 != 0 else None,
        'Ethos_Guid__c': f'ethos-{idx:08d}' if idx % 11 != 0 else None,
        'PersonEmail': f'student{idx}@doane.edu',
        'PersonBirthdate': '2000-01-15',
        'attributes': {'type': 'Account', 'url': f'/services/data/v59.0/sobjects/Account/001{idx:015d}'},
    }


def _make_contactpoint_email(idx: int, account_id: Optional[str] = None) -> dict:
    return {
        # TODO(salesforce): confirm ContactPointEmail field API names
        'Id': f'0re{idx:015d}',
        'EmailAddress': f'student{idx}@doane.edu',
        'ParentId': account_id or (f'001{idx:015d}' if idx % 6 != 0 else None),
        'IndividualId': f'ind{idx:015d}' if idx % 8 != 0 else None,
        'SIS_ID__c': f'STU{idx:05d}' if idx % 5 != 0 else None,
        'IsPrimary': idx % 3 == 0,
        'attributes': {'type': 'ContactPointEmail'},
    }


def _make_contactpoint_phone(idx: int) -> dict:
    return {
        # TODO(salesforce): confirm ContactPointPhone field API names
        'Id': f'0rf{idx:015d}',
        'TelephoneNumber': f'402-555-{idx:04d}',
        'ParentId': f'001{idx:015d}' if idx % 6 != 0 else None,
        'IndividualId': f'ind{idx:015d}' if idx % 9 != 0 else None,
        'SIS_ID__c': f'STU{idx:05d}' if idx % 5 != 0 else None,
        'attributes': {'type': 'ContactPointPhone'},
    }


def _make_contactpoint_address(idx: int) -> dict:
    return {
        # TODO(salesforce): confirm ContactPointAddress field API names
        'Id': f'0rg{idx:015d}',
        'Street': f'{idx} Main St',
        'City': 'Crete',
        'State': 'NE',
        'PostalCode': '68333',
        'ParentId': f'001{idx:015d}' if idx % 6 != 0 else None,
        'IndividualId': f'ind{idx:015d}' if idx % 7 != 0 else None,
        'SIS_ID__c': f'STU{idx:05d}' if idx % 5 != 0 else None,
        'attributes': {'type': 'ContactPointAddress'},
    }


def _describe_field(name: str, label: str, field_type: str, required: bool = False,
                    external_id: bool = False) -> dict:
    return {
        'name': name,
        'label': label,
        'type': field_type,
        'nillable': not required,
        'externalId': external_id,
        'custom': name.endswith('__c'),
        'calculated': False,
        'picklistValues': [],
    }


_DESCRIBE_CACHE: Dict[str, dict] = {}


def _build_describe(obj: str) -> dict:
    if obj == 'Account':
        fields = [
            _describe_field('Id', 'Record ID', 'id'),
            _describe_field('Name', 'Full Name', 'string', required=True),
            _describe_field('IsPersonAccount', 'Is Person Account', 'boolean'),
            _describe_field('SIS_ID__c', 'SIS ID', 'string', external_id=True),
            _describe_field('Ethos_Guid__c', 'Ethos GUID', 'string', external_id=True),
            _describe_field('PersonEmail', 'Email', 'email'),
            _describe_field('PersonBirthdate', 'Birthdate', 'date'),
        ]
    elif obj == 'ContactPointEmail':
        fields = [
            _describe_field('Id', 'Record ID', 'id'),
            _describe_field('EmailAddress', 'Email Address', 'email', required=True),
            _describe_field('ParentId', 'Parent ID', 'reference'),
            _describe_field('IndividualId', 'Individual ID', 'reference'),
            _describe_field('SIS_ID__c', 'SIS ID', 'string', external_id=True),
            _describe_field('IsPrimary', 'Is Primary', 'boolean'),
        ]
    elif obj == 'ContactPointPhone':
        fields = [
            _describe_field('Id', 'Record ID', 'id'),
            _describe_field('TelephoneNumber', 'Phone Number', 'phone', required=True),
            _describe_field('ParentId', 'Parent ID', 'reference'),
            _describe_field('IndividualId', 'Individual ID', 'reference'),
            _describe_field('SIS_ID__c', 'SIS ID', 'string', external_id=True),
        ]
    elif obj == 'ContactPointAddress':
        fields = [
            _describe_field('Id', 'Record ID', 'id'),
            _describe_field('Street', 'Street', 'textarea'),
            _describe_field('City', 'City', 'string'),
            _describe_field('State', 'State', 'string'),
            _describe_field('PostalCode', 'Postal Code', 'string'),
            _describe_field('ParentId', 'Parent ID', 'reference'),
            _describe_field('IndividualId', 'Individual ID', 'reference'),
            _describe_field('SIS_ID__c', 'SIS ID', 'string', external_id=True),
        ]
    else:
        fields = [_describe_field('Id', 'Record ID', 'id')]

    return {
        'name': obj,
        'label': obj,
        'fields': fields,
        'queryable': True,
        'updateable': True,
        'createable': True,
    }


# ── mock DML object ───────────────────────────────────────────────────────────

class _MockSFObject:
    """Simulates a simple_salesforce SObject (e.g. sf.Account)."""

    def __init__(self, object_name: str) -> None:
        self._name = object_name

    def upsert(self, external_id_field_value: str, data: dict) -> dict:
        """Return a mock upsert result."""
        return {
            'id': f'mock-{self._name}-001',
            'success': True,
            'errors': [],
            'created': True,
        }

    def get(self, record_id: str) -> dict:
        return {'Id': record_id, 'attributes': {'type': self._name}}

    def update(self, record_id: str, data: dict) -> int:
        return 204


# ── MockSalesforce ─────────────────────────────────────────────────────────────

class MockSalesforce:
    """Minimal Salesforce mock that returns data matching the handoff doc numbers."""

    def __init__(self, org: str = 'dev') -> None:
        self.org = org
        self.base_url = 'https://mock.salesforce.com/services/data/v59.0/'
        # Expose SObject-style attributes
        self.Account = _MockSFObject('Account')
        self.ContactPointEmail = _MockSFObject('ContactPointEmail')
        self.ContactPointPhone = _MockSFObject('ContactPointPhone')
        self.ContactPointAddress = _MockSFObject('ContactPointAddress')

    # -- query ----------------------------------------------------------------

    def query(self, soql: str) -> dict:
        """Return mock query result (up to 200 records)."""
        records = self._mock_records(soql, limit=200)
        return {
            'totalSize': _parse_mock_count(soql),
            'done': True,
            'records': records,
        }

    def query_all(self, soql: str) -> dict:
        """Return mock full-result query (larger record set)."""
        total = _parse_mock_count(soql)
        records = self._mock_records(soql, limit=min(total, 500))
        return {
            'totalSize': total,
            'done': True,
            'records': records,
        }

    def query_more(self, next_records_url: str, identifier: bool = False) -> dict:
        return {'totalSize': 0, 'done': True, 'records': []}

    # -- restful (describe) ---------------------------------------------------

    def restful(self, path: str, method: str = 'GET', **kwargs) -> Any:
        """Return mock describe or explain responses."""
        path_lower = path.lower()

        if 'sobjects' in path_lower and 'describe' in path_lower:
            parts = path.split('/')
            try:
                obj_idx = parts.index('sobjects') + 1
                obj_name = parts[obj_idx]
            except (ValueError, IndexError):
                obj_name = 'Unknown'
            return _build_describe(obj_name)

        if 'sobjects' in path_lower and 'describe' not in path_lower:
            # DescribeGlobal
            return {
                'sobjects': [
                    {'name': o, 'label': o, 'queryable': True, 'custom': o.endswith('__c')}
                    for o in ['Account', 'ContactPointEmail', 'ContactPointPhone',
                               'ContactPointAddress', 'IndividualApplication', 'Opportunity']
                ]
            }

        if 'query/explain' in path_lower or 'explain' in path_lower:
            return {
                'plans': [{
                    'cardinality': 4312,
                    'fields': [],
                    'leadingOperationType': 'TableScan',
                    'notes': [],
                    'relativeCost': 1.0,
                    'sobjectCardinality': 4312,
                    'sobjectType': 'Account',
                }]
            }

        return {}

    # -- private helpers ------------------------------------------------------

    def _mock_records(self, soql: str, limit: int = 200) -> List[dict]:
        soql_lower = soql.lower()
        records: List[dict] = []

        if 'contactpointaddress' in soql_lower:
            for i in range(1, limit + 1):
                records.append(_make_contactpoint_address(i))
        elif 'contactpointemail' in soql_lower:
            for i in range(1, limit + 1):
                records.append(_make_contactpoint_email(i))
        elif 'contactpointphone' in soql_lower:
            for i in range(1, limit + 1):
                records.append(_make_contactpoint_phone(i))
        elif 'account' in soql_lower or 'personaccount' in soql_lower:
            for i in range(1, limit + 1):
                records.append(_make_person_account(i))
        else:
            for i in range(1, min(limit, 10) + 1):
                records.append({'Id': f'gen{i:015d}', 'attributes': {'type': 'GenericObject'}})

        return records


# ── public factory ─────────────────────────────────────────────────────────────

def get_sf(org: str = 'dev'):
    """Return a Salesforce client (real or mock) for the given org."""
    if Config.SF_MOCK or not _configured(org):
        logger.info("SF_MOCK active — using MockSalesforce for org '%s'", org)
        return MockSalesforce(org)

    from simple_salesforce import Salesforce  # type: ignore
    cfg = get_org_config(org)
    logger.info("Connecting to real Salesforce org '%s' as %s (API v%s)", org, cfg['username'], cfg['api_version'])
    return Salesforce(
        username=cfg['username'],
        password=cfg['password'],
        security_token=cfg['security_token'],
        domain=cfg['domain'],
        version=cfg['api_version'],
    )
