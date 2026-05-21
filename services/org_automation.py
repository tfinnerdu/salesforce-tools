"""Org Automation & Sharing — validation rules, flows, triggers, OWD sharing model.

Surfaces config that is normally buried behind many clicks in Setup. All read-only.
"""
import logging

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)


# ── Validation Rules ──────────────────────────────────────────────────────────

def get_validation_rules(org: str) -> list:
    """List all validation rules across the org (Tooling API).

    The Tooling API cannot ORDER BY a cross-entity relationship field over
    every ValidationRule — doing so triggers an UNKNOWN_EXCEPTION. The query
    is bounded with LIMIT and sorted in Python instead.
    """
    sf = get_sf(org)
    soql = (
        "SELECT Id, ValidationName, Active, Description, ErrorMessage, "
        "ErrorDisplayField, EntityDefinition.QualifiedApiName "
        "FROM ValidationRule LIMIT 2000"
    )
    try:
        res = sf.restful('tooling/query/', params={'q': soql})
        records = res.get('records', [])
        rules = []
        for r in records:
            ent = r.get('EntityDefinition') or {}
            rules.append({
                'id': r.get('Id'),
                'name': r.get('ValidationName', ''),
                'object': ent.get('QualifiedApiName', '') if isinstance(ent, dict) else '',
                'active': bool(r.get('Active', False)),
                'error_message': r.get('ErrorMessage', '') or '',
                'error_field': r.get('ErrorDisplayField', '') or '',
                'description': r.get('Description', '') or '',
            })
        rules.sort(key=lambda x: (x['object'], x['name']))
        if Config.SF_MOCK and not rules:
            return _mock_validation_rules()
        return rules
    except Exception as exc:
        logger.warning('validation rule query failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_validation_rules()
        raise


def _mock_validation_rules() -> list:
    return [
        {'id': 'VR001', 'name': 'Require_SIS_ID', 'object': 'Account', 'active': True,
         'error_message': 'SIS ID is required for all Person Accounts', 'error_field': 'SIS_ID__c',
         'description': 'Ensures every migrated PersonAccount has a Colleague SIS ID'},
        {'id': 'VR002', 'name': 'Valid_Ethos_Guid_Format', 'object': 'Account', 'active': True,
         'error_message': 'Ethos GUID must be a valid 36-char UUID', 'error_field': 'Ethos_Guid__c',
         'description': 'Format check on the Ethos LDM GUID'},
        {'id': 'VR003', 'name': 'ContactPoint_Parent_Required', 'object': 'ContactPointEmail', 'active': True,
         'error_message': 'ContactPoint must parent to an Account or Individual', 'error_field': 'ParentId',
         'description': ''},
        {'id': 'VR004', 'name': 'Legacy_EDA_Block', 'object': 'Contact', 'active': False,
         'error_message': 'EDA Contact creation is disabled during Ed Cloud migration', 'error_field': '',
         'description': 'Disabled rule — kept for reference'},
    ]


# ── Flows ─────────────────────────────────────────────────────────────────────

def get_flows(org: str) -> list:
    """List flows via the FlowDefinitionView Data API object.

    FlowDefinition (Tooling API) has no ProcessType or Status columns.
    FlowDefinitionView is the queryable view that exposes flow type and
    active status, and it lives on the regular Data API.
    """
    sf = get_sf(org)
    soql = (
        "SELECT DurableId, ApiName, Label, ProcessType, TriggerType, IsActive, "
        "Description, LastModifiedDate "
        "FROM FlowDefinitionView ORDER BY Label"
    )
    try:
        res = sf.query_all(soql)
        records = res.get('records', [])
        flows = []
        for r in records:
            flows.append({
                'id': r.get('DurableId') or r.get('ApiName', ''),
                'name': r.get('ApiName', ''),
                'label': r.get('Label', '') or r.get('ApiName', ''),
                'type': r.get('ProcessType', '') or '',
                'trigger_type': r.get('TriggerType', '') or '',
                'status': 'Active' if r.get('IsActive') else 'Inactive',
                'description': r.get('Description', '') or '',
                'last_modified': r.get('LastModifiedDate', ''),
            })
        if Config.SF_MOCK and not flows:
            return _mock_flows()
        return flows
    except Exception as exc:
        logger.warning('flow query failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_flows()
        raise


def _mock_flows() -> list:
    return [
        {'id': 'FL001', 'name': 'Student_Update_Handler', 'label': 'Student Update Handler',
         'type': 'AutoLaunchedFlow', 'trigger_type': 'RecordAfterSave', 'status': 'Active',
         'description': 'Record-triggered flow on Account update', 'last_modified': '2026-05-18T10:00:00Z'},
        {'id': 'FL002', 'name': 'Migration_Complete_Notifier', 'label': 'Migration Complete Notifier',
         'type': 'AutoLaunchedFlow', 'trigger_type': 'PlatformEvent', 'status': 'Active',
         'description': 'Sends notification on Migration_Complete__e', 'last_modified': '2026-05-15T14:30:00Z'},
        {'id': 'FL003', 'name': 'ContactPoint_Dedupe', 'label': 'ContactPoint Dedupe',
         'type': 'Workflow', 'trigger_type': '', 'status': 'Inactive',
         'description': 'Legacy process builder — superseded', 'last_modified': '2025-11-02T09:00:00Z'},
    ]


# ── Apex Triggers ─────────────────────────────────────────────────────────────

def get_apex_triggers(org: str) -> list:
    """List Apex triggers and the objects they run on (Tooling API)."""
    sf = get_sf(org)
    soql = (
        "SELECT Id, Name, Status, ApiVersion, LengthWithoutComments, "
        "EntityDefinition.QualifiedApiName "
        "FROM ApexTrigger "
        "ORDER BY Name"
    )
    try:
        res = sf.restful('tooling/query/', params={'q': soql})
        records = res.get('records', [])
        triggers = []
        for r in records:
            ent = r.get('EntityDefinition') or {}
            triggers.append({
                'id': r.get('Id'),
                'name': r.get('Name', ''),
                'object': ent.get('QualifiedApiName', '') if isinstance(ent, dict) else '',
                'status': r.get('Status', '') or '',
                'api_version': r.get('ApiVersion', ''),
                'length': r.get('LengthWithoutComments', 0) or 0,
            })
        if Config.SF_MOCK and not triggers:
            return _mock_triggers()
        return triggers
    except Exception as exc:
        logger.warning('apex trigger query failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_triggers()
        raise


def _mock_triggers() -> list:
    return [
        {'id': 'TR001', 'name': 'AccountTrigger', 'object': 'Account', 'status': 'Active',
         'api_version': 59.0, 'length': 1840},
        {'id': 'TR002', 'name': 'ContactPointEmailTrigger', 'object': 'ContactPointEmail', 'status': 'Active',
         'api_version': 59.0, 'length': 620},
        {'id': 'TR003', 'name': 'IndividualTrigger', 'object': 'Individual', 'status': 'Inactive',
         'api_version': 58.0, 'length': 410},
    ]


# ── Sharing Model (Org-Wide Defaults) ─────────────────────────────────────────

_SHARING_LABELS = {
    'Private': 'Private',
    'Read': 'Public Read Only',
    'ReadSelect': 'Public Read Only',
    'Edit': 'Public Read/Write',
    'ReadWrite': 'Public Read/Write',
    'ReadWriteTransfer': 'Public Read/Write/Transfer',
    'FullAccess': 'Public Full Access',
    'ControlledByParent': 'Controlled by Parent',
    'ControlledByCampaign': 'Controlled by Campaign',
    'ControlledByLeadOrContact': 'Controlled by Lead or Contact',
}


def get_sharing_model(org: str) -> list:
    """List org-wide default sharing settings per object (Tooling API EntityDefinition)."""
    sf = get_sf(org)
    # EntityDefinition does not support queryMore() — a LIMIT is required to
    # keep the result within a single batch, or the query fails outright.
    soql = (
        "SELECT QualifiedApiName, Label, InternalSharingModel, ExternalSharingModel "
        "FROM EntityDefinition "
        "WHERE InternalSharingModel != null "
        "ORDER BY Label LIMIT 2000"
    )
    try:
        res = sf.restful('tooling/query/', params={'q': soql})
        records = res.get('records', [])
        rows = []
        for r in records:
            internal = r.get('InternalSharingModel', '') or ''
            external = r.get('ExternalSharingModel', '') or ''
            rows.append({
                'object': r.get('QualifiedApiName', ''),
                'label': r.get('Label', '') or r.get('QualifiedApiName', ''),
                'internal': internal,
                'internal_label': _SHARING_LABELS.get(internal, internal),
                'external': external,
                'external_label': _SHARING_LABELS.get(external, external),
                'is_private': internal == 'Private',
            })
        if Config.SF_MOCK and not rows:
            return _mock_sharing_model()
        return rows
    except Exception as exc:
        logger.warning('sharing model query failed: %s', exc)
        if Config.SF_MOCK:
            return _mock_sharing_model()
        raise


def _mock_sharing_model() -> list:
    raw = [
        ('Account', 'Account', 'Private', 'Private'),
        ('Contact', 'Contact', 'ControlledByParent', 'ControlledByParent'),
        ('Case', 'Case', 'Private', 'Private'),
        ('Lead', 'Lead', 'ReadWrite', 'Read'),
        ('Individual', 'Individual', 'ReadWrite', 'Private'),
        ('ContactPointEmail', 'Contact Point Email', 'ControlledByParent', 'ControlledByParent'),
    ]
    return [
        {'object': o, 'label': lbl, 'internal': i, 'internal_label': _SHARING_LABELS.get(i, i),
         'external': e, 'external_label': _SHARING_LABELS.get(e, e), 'is_private': i == 'Private'}
        for o, lbl, i, e in raw
    ]


# ── Convenience ───────────────────────────────────────────────────────────────

def get_all(org: str) -> dict:
    return {
        'validation_rules': get_validation_rules(org),
        'flows': get_flows(org),
        'triggers': get_apex_triggers(org),
        'sharing_model': get_sharing_model(org),
    }
