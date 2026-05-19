"""Salesforce provider — returns real simple_salesforce client or a mock."""
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from config import Config, get_org_config

logger = logging.getLogger(__name__)

# ── DML helpers ───────────────────────────────────────────────────────────────

_dml_lock = threading.Lock()
_last_dml_time: float = 0.0


def dml_throttle() -> None:
    """Sleep if needed to honour SF_DML_RATE_LIMIT (calls/sec). No-op when 0."""
    rate = Config.SF_DML_RATE_LIMIT
    if not rate:
        return
    global _last_dml_time
    with _dml_lock:
        elapsed = time.monotonic() - _last_dml_time
        min_gap = 1.0 / rate
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        _last_dml_time = time.monotonic()


def set_bypass_triggers(sf, enable: bool) -> None:
    """Flip the org-level bypass-triggers Custom Setting via REST. No-op when unconfigured."""
    setting = Config.SF_BYPASS_SETTING
    field = Config.SF_BYPASS_FIELD
    if not setting or not field:
        return
    try:
        sf.restful(f'sobjects/{setting}/', method='PATCH', json={field: enable})
        logger.info("bypass_triggers set to %s on %s", enable, setting)
    except Exception as exc:
        logger.warning("set_bypass_triggers(%s) failed: %s", enable, exc)


@contextmanager
def dml_guard(sf, bypass: bool = False) -> Generator:
    """Rate-throttle and optionally bypass Apex triggers around a DML block."""
    dml_throttle()
    if bypass:
        set_bypass_triggers(sf, True)
    try:
        yield
    finally:
        if bypass:
            set_bypass_triggers(sf, False)


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


def _make_perm_set_assignment(idx: int) -> dict:
    return {
        'Id': f'0Pa{idx:015d}',
        'PermissionSet': {
            'Name': f'PS_DataEntry_{idx}',
            'Label': f'Data Entry {idx}',
            'IsOwnedByProfile': False,
        },
        'Assignee': {
            'Name': f'User {idx}',
            'Username': f'user{idx}@doane.edu',
        },
        'attributes': {'type': 'PermissionSetAssignment'},
    }


def _make_field_permission(idx: int) -> dict:
    return {
        'Id': f'0PS{idx:015d}',
        'SobjectType': 'Account',
        'Field': 'Account.SIS_ID__c' if idx % 3 == 0 else 'Account.Ethos_Guid__c',
        'PermissionsRead': True,
        'PermissionsEdit': idx % 2 == 0,
        'attributes': {'type': 'FieldPermissions'},
    }


def _make_validation_rule(idx: int) -> dict:
    return {
        'Id': f'03N{idx:015d}',
        'EntityDefinition': {'QualifiedApiName': 'Account'},
        'ValidationName': f'Require_SIS_ID_{idx}',
        'Description': 'SIS ID required on save',
        'ErrorMessage': 'SIS ID cannot be blank',
        'attributes': {'type': 'ValidationRule'},
    }


def _make_flow_definition(idx: int) -> dict:
    return {
        'Id': f'301{idx:015d}',
        'MasterLabel': f'Sync Student Record {idx}',
        'ProcessType': 'AutoLaunchedFlow',
        'Status': 'Active',
        'Description': 'Syncs student data from SIS',
        'attributes': {'type': 'FlowDefinition'},
    }


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


# ── mock Tooling API data factories ───────────────────────────────────────────

_MOCK_LOG_BODY = """\
09:00:00.0 (1)|EXECUTION_STARTED
09:00:00.1 (2)|CODE_UNIT_STARTED|[EXTERNAL]|01q...|MyTrigger on Account trigger event BeforeInsert
09:00:00.5 (3)|SOQL_EXECUTE_BEGIN|[12]|Aggregations:0|SELECT Id FROM Account WHERE SIS_ID__c = :sisId
09:00:00.6 (4)|SOQL_EXECUTE_END|[12]|Rows:1
09:00:01.0 (5)|DML_BEGIN|[25]|Op:Insert|Type:Account|Rows:1
09:00:01.2 (6)|DML_END|[25]
09:00:01.3 (7)|CODE_UNIT_FINISHED|MyTrigger on Account
09:00:01.4 (8)|EXECUTION_FINISHED
10:17:00.0 (100)|LIMIT_USAGE_FOR_NS|(default)|
  Number of SOQL queries: 3 out of 100
  Number of query rows: 15 out of 50000
  Number of SOQL queries for Apex jobs: 0 out of 0
  Number of DML statements: 1 out of 150
  Number of DML rows: 1 out of 10000
  Maximum CPU time: 180 out of 10000
  Maximum heap size: 0 out of 6000000
  Number of callouts: 0 out of 100
  Number of Email Invocations: 0 out of 10
  Number of future calls: 0 out of 50
  Number of queueable jobs added to the queue: 0 out of 50
  Number of Mobile Apex push calls: 0 out of 10
"""


def _make_apex_log(idx: int) -> dict:
    return {
        'Id': f'07L{idx:015d}',
        'LogUser': {'Name': f'User {idx}', 'attributes': {'type': 'User'}},
        'Operation': '/apex/MyPage' if idx % 3 == 0 else 'API',
        'Application': 'Unknown Application',
        'Status': 'Success' if idx % 5 != 0 else 'Truncated',
        'LogLength': 45000 + idx * 1000,
        'DurationMilliseconds': 200 + idx * 50,
        'LastModifiedDate': '2026-05-19T10:00:00.000+0000',
        'attributes': {'type': 'ApexLog'},
    }


_FLOW_ELEMENTS = [
    'Update_Account_Record',
    'Create_Enrollment_Record',
    'Get_SIS_Data',
    'Send_Confirmation_Email',
    'Check_Duplicate_Account',
    'Assign_Advisor',
    'Update_Stage',
]

_FLOW_ERRORS = [
    'FIELD_CUSTOM_VALIDATION_EXCEPTION: SIS ID is required.',
    'CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY: PersonAccount trigger threw unhandled exception.',
    'FIELD_INTEGRITY_EXCEPTION: Account.PersonEmail: value not valid.',
    'REQUIRED_FIELD_MISSING: Required fields are missing: [LastName]',
    'DUPLICATE_VALUE: duplicate value found: SIS_ID__c',
    'UNABLE_TO_LOCK_ROW: unable to obtain exclusive access to this record',
]


def _make_flow_interview(idx: int) -> dict:
    element = _FLOW_ELEMENTS[idx % len(_FLOW_ELEMENTS)]
    error = _FLOW_ERRORS[idx % len(_FLOW_ERRORS)]
    return {
        'Id': f'0lM{idx:015d}',
        'FlowVersionId': f'301{idx:015d}',
        'InterviewStatus': 'Error',
        'CurrentElement': element,
        'ErrorMessage': f'An error occurred at element {element}. {error}',
        'StartInterviewTime': '2026-05-19T09:30:00.000+0000',
        'EndInterviewTime': '2026-05-19T09:30:01.000+0000',
        'attributes': {'type': 'FlowInterview'},
    }


_PROC_EX_TYPES = ['FlowException', 'ValidationException', 'DmlException']
_PROC_EX_MSGS = [
    'Record could not be saved due to a flow error.',
    'Validation rule failed: SIS ID must not be blank.',
    'Insert failed: required field missing.',
    'Flow interview ended with unhandled fault.',
    'DML operation failed on Account.',
]
_PROC_EX_OBJECTS = ['Account', 'ContactPointEmail', 'IndividualApplication']


def _make_cron_trigger(idx: int) -> dict:
    states = ['WAITING', 'WAITING', 'WAITING', 'PAUSED', 'ERROR']
    return {
        'Id': f'08e{idx:015d}',
        'CronJobDetail': {'Name': f'Nightly_Sync_Job_{idx}', 'JobType': '7'},
        'State': states[idx % len(states)],
        'NextFireTime': '2026-05-20T06:00:00.000+0000',
        'PreviousFireTime': '2026-05-19T06:00:00.000+0000',
        'StartTime': '2026-01-01T00:00:00.000+0000',
        'TimesTriggered': 140 + idx,
        'CronExpression': '0 0 6 * * ?',
        'attributes': {'type': 'CronTrigger'},
    }


def _make_sf_user(idx: int) -> dict:
    days_ago = [1, 5, 30, 95, None]
    last_login = None if days_ago[idx % 5] is None else f'2026-0{5 - (idx % 3):01d}-{max(1, 19 - days_ago[idx % 5] % 28):02d}T10:00:00.000+0000'
    return {
        'Id': f'005{idx:015d}',
        'Name': f'User {idx}',
        'Username': f'user{idx}@doane.edu',
        'IsActive': idx % 8 != 0,
        'LastLoginDate': last_login,
        'UserType': 'Standard',
        'Profile': {'Name': 'System Administrator' if idx % 10 == 0 else 'Standard User'},
        'CreatedDate': '2024-01-15T00:00:00.000+0000',
        'attributes': {'type': 'User'},
    }


def _make_process_exception(idx: int) -> dict:
    return {
        'Id': f'0pE{idx:015d}',
        'ExceptionType': _PROC_EX_TYPES[idx % len(_PROC_EX_TYPES)],
        'Message': _PROC_EX_MSGS[idx % len(_PROC_EX_MSGS)],
        'Status': 'Pending',
        'SourceId': f'001{idx:015d}',
        'SourceObjectApiName': _PROC_EX_OBJECTS[idx % len(_PROC_EX_OBJECTS)],
        'CreatedDate': '2026-05-19T08:00:00.000+0000',
        'attributes': {'type': 'ProcessException'},
    }


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
        self.sf_instance = 'mock.salesforce.com'
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

        # ── Tooling API ──────────────────────────────────────────────────────
        if 'tooling' in path_lower:
            if 'tooling/query' in path_lower:
                params = kwargs.get('params', {})
                q_str = params.get('q', path)
                q_lower = q_str.lower() if isinstance(q_str, str) else path_lower
                if 'validationrule' in q_lower:
                    records = [_make_validation_rule(i) for i in range(1, 6)]
                    return {'totalSize': 5, 'done': True, 'records': records}
                if 'flowdefinition' in q_lower:
                    records = [_make_flow_definition(i) for i in range(1, 8)]
                    return {'totalSize': 7, 'done': True, 'records': records}
                if 'apexcodecoverageaggregate' in q_lower:
                    records = [
                        {
                            'Id': f'apxcov{i:010d}',
                            'ApexClassOrTrigger': {'Name': 'AccountTriggerHandler' if i % 3 == 0 else f'StudentSyncService_{i}'},
                            'ApexClassOrTriggerId': f'01p{i:015d}',
                            'NumLinesCovered': 80 + (i * 3 % 40),
                            'NumLinesUncovered': i * 2 % 30,
                            'attributes': {'type': 'ApexCodeCoverageAggregate'},
                        }
                        for i in range(1, 16)
                    ]
                    return {'totalSize': len(records), 'done': True, 'records': records}
                if 'deployrequest' in q_lower:
                    records = [
                        {
                            'Id': f'0Af{i:015d}',
                            'Status': 'Succeeded' if i % 4 != 0 else 'Failed',
                            'StartDate': '2026-05-19T08:00:00.000+0000',
                            'CompletedDate': '2026-05-19T08:04:32.000+0000',
                            'CreatedBy': {'Name': f'Dev User {i}'},
                            'NumberComponentsTotal': 12 + i * 3,
                            'NumberComponentErrors': 0 if i % 4 != 0 else 2,
                            'NumberTestsCompleted': 45,
                            'NumberTestErrors': 0 if i % 4 != 0 else 1,
                            'StateDetail': None if i % 4 != 0 else 'Test failure: AccountTest.testInsert',
                            'attributes': {'type': 'DeployRequest'},
                        }
                        for i in range(1, 11)
                    ]
                    return {'totalSize': len(records), 'done': True, 'records': records}
                if 'apexlog' in q_lower:
                    records = [_make_apex_log(i) for i in range(1, 11)]
                    return {'totalSize': 10, 'done': True, 'records': records}
                if 'flowinterview' in q_lower:
                    records = [_make_flow_interview(i) for i in range(1, 7)]
                    return {'totalSize': 6, 'done': True, 'records': records}
                if 'processexception' in q_lower:
                    records = [_make_process_exception(i) for i in range(1, 5)]
                    return {'totalSize': 4, 'done': True, 'records': records}
                if 'customfield' in q_lower:
                    objects = ['Account', 'Account', 'Account', 'ContactPointEmail', 'ContactPointEmail']
                    fields = ['SIS_ID__c', 'Ethos_Guid__c', 'Legacy_ID__c', 'SIS_ID__c', 'Source_System__c']
                    labels = ['SIS ID', 'Ethos GUID', 'Legacy ID', 'SIS ID', 'Source System']
                    records = [
                        {
                            'Id': f'00N{i:015d}',
                            'DeveloperName': fields[i - 1].replace('__c', ''),
                            'Label': labels[i - 1],
                            'EntityDefinition': {'QualifiedApiName': objects[i - 1]},
                            'attributes': {'type': 'CustomField'},
                        }
                        for i in range(1, 6)
                    ]
                    return {'totalSize': 5, 'done': True, 'records': records}
                return {'totalSize': 0, 'done': True, 'records': []}

            if 'tooling/sobjects/apexlog' in path_lower:
                if method.upper() == 'DELETE':
                    return {}
                if path_lower.endswith('/body'):
                    return _MOCK_LOG_BODY
                return {}

            return {}

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

        if 'limits' in path_lower and 'sobjects' not in path_lower and 'query' not in path_lower:
            return self._mock_limits()

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

        if 'crontrigger' in soql_lower:
            for i in range(1, min(limit, 10) + 1):
                records.append(_make_cron_trigger(i))
        elif 'from user' in soql_lower or ("select" in soql_lower and "'standard'" in soql_lower):
            for i in range(1, min(limit, 25) + 1):
                records.append(_make_sf_user(i))
        elif 'permissionsetassignment' in soql_lower:
            for i in range(1, min(limit, 20) + 1):
                records.append(_make_perm_set_assignment(i))
        elif 'fieldpermissions' in soql_lower:
            for i in range(1, min(limit, 30) + 1):
                records.append(_make_field_permission(i))
        elif 'report' in soql_lower and 'contactpoint' not in soql_lower:
            for i in range(1, min(limit, 12) + 1):
                records.append({
                    'Id': f'00O{i:015d}',
                    'Name': f'Student Report {i}',
                    'FolderName': 'Enrollment Reports',
                    'LastRunDate': '2026-05-01',
                    'attributes': {'type': 'Report'},
                })
        elif 'apexclass' in soql_lower:
            for i in range(1, min(limit, 12) + 1):
                name = (
                    'StudentSyncService' if i == 1
                    else 'AccountTriggerHandler' if i == 2
                    else f'EthosIntegrationUtil_{i}'
                )
                records.append({
                    'Id': f'01p{i:015d}',
                    'Name': name,
                    'LastModifiedDate': '2026-05-19T10:00:00.000+0000',
                    'attributes': {'type': 'ApexClass'},
                })
        elif 'apextrigger' in soql_lower:
            for i in range(1, min(limit, 4) + 1):
                records.append({
                    'Id': f'01q{i:015d}',
                    'Name': f'AccountTrigger' if i == 1 else f'ContactPointTrigger_{i}',
                    'TableEnumOrId': 'Account' if i == 1 else 'ContactPointEmail',
                    'attributes': {'type': 'ApexTrigger'},
                })
        elif 'flowdefinition' in soql_lower:
            for i in range(1, min(limit, 5) + 1):
                records.append({
                    'Id': f'301{i:015d}',
                    'DeveloperName': f'Sync_Student_Record_{i}',
                    'MasterLabel': f'Sync Student Record {i}',
                    'ProcessType': 'AutoLaunchedFlow',
                    'Status': 'Active',
                    'attributes': {'type': 'FlowDefinition'},
                })
        elif 'permissionset' in soql_lower and 'assignment' not in soql_lower:
            for i in range(1, min(limit, 6) + 1):
                records.append({
                    'Id': f'0PS{i:015d}',
                    'Name': f'Migration_User_PS_{i}',
                    'Label': f'Migration User {i}',
                    'IsOwnedByProfile': False,
                    'attributes': {'type': 'PermissionSet'},
                })
        elif 'contactpointaddress' in soql_lower:
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

    def _mock_limits(self) -> dict:
        org = self.org
        if org == 'prod':
            daily_remaining = 8100
            bulk_remaining = 5200
            async_remaining = 180000
        elif org == 'sandbox':
            daily_remaining = 14900
            bulk_remaining = 9950
            async_remaining = 249800
        else:  # dev
            daily_remaining = 14523
            bulk_remaining = 9800
            async_remaining = 249100
        return {
            'DailyApiRequests': {'Max': 15000, 'Remaining': daily_remaining},
            'DataStorageMB': {'Max': 5120, 'Remaining': 5120 - (200 if org == 'prod' else 50)},
            'FileStorageMB': {'Max': 20480, 'Remaining': 20480 - (480 if org == 'prod' else 100)},
            'DailyBulkApiRequests': {'Max': 10000, 'Remaining': bulk_remaining},
            'DailyWorkflowEmails': {'Max': 1000, 'Remaining': 987 if org != 'prod' else 650},
            'MassEmail': {'Max': 5000, 'Remaining': 5000},
            'SingleEmail': {'Max': 5000, 'Remaining': 4990 if org != 'prod' else 4500},
            'DailyDurableStreamingApiEvents': {'Max': 10000, 'Remaining': 10000},
            'DailyAsyncApexExecutions': {'Max': 250000, 'Remaining': async_remaining},
            'DailyBulkV2QueryJobs': {'Max': 10000, 'Remaining': 9990 if org != 'prod' else 9100},
        }


# ── public factory ─────────────────────────────────────────────────────────────

def get_sf(org: str = 'dev'):
    """Return a Salesforce client (real or mock) for the given org."""
    if Config.SF_MOCK or not _configured(org):
        logger.info("SF_MOCK active — using MockSalesforce for org '%s'", org)
        return MockSalesforce(org)

    from simple_salesforce import Salesforce  # type: ignore
    cfg = get_org_config(org)
    api_version = cfg['api_version']
    # SOAP login endpoint rejects versions above ~59; authenticate with capped version
    # then upgrade base_url so all REST calls use the configured API version.
    soap_version = Config.SF_SOAP_AUTH_VERSION
    logger.info("Connecting to real Salesforce org '%s' as %s (auth v%s → API v%s)",
                org, cfg['username'], soap_version, api_version)
    sf = Salesforce(
        username=cfg['username'],
        password=cfg['password'],
        security_token=cfg['security_token'],
        domain=cfg['domain'],
        version=soap_version,
    )
    if api_version != soap_version:
        sf.sf_version = api_version
        sf.base_url = f"https://{sf.sf_instance}/services/data/v{api_version}/"
    return sf
