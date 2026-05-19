"""Change Set Builder — queries SF for deployable metadata components and builds package.xml."""
import logging
from xml.sax.saxutils import escape as xml_escape

from sf_provider import get_sf

logger = logging.getLogger(__name__)

# Human-readable type labels used in the checklist output
_TYPE_LABELS = {
    'ApexClass': 'Apex Class',
    'ApexTrigger': 'Apex Trigger',
    'CustomField': 'Custom Field',
    'Flow': 'Flow',
    'PermissionSet': 'Permission Set',
    'ValidationRule': 'Validation Rule',
}

# Setup UI navigation paths for manual change-set workflow
_SETUP_PATHS = {
    'ApexClass': 'Setup → Apex Classes',
    'ApexTrigger': 'Setup → Apex Classes (Triggers tab)',
    'CustomField': 'Setup → Object Manager → {object} → Fields & Relationships',
    'Flow': 'Setup → Flows',
    'PermissionSet': 'Setup → Permission Sets',
    'ValidationRule': 'Setup → Object Manager → {object} → Validation Rules',
}


def _setup_path(type_name: str, member: str) -> str:
    """Return human-readable Setup navigation path for a component."""
    template = _SETUP_PATHS.get(type_name, '')
    if '{object}' in template:
        # member format is ObjectName.ComponentName
        obj = member.split('.')[0] if '.' in member else member
        return template.replace('{object}', obj)
    return template


def list_components(org: str, component_type: str) -> list:
    """Query Salesforce and return deployable components for the given type.

    Returns a list of dicts: {member: str, type: str, label: str}.
    ``member`` is the exact string used in package.xml; ``label`` is a
    human-readable display string shown in the UI picker.
    """
    sf = get_sf(org)
    components: list = []

    if component_type == 'ApexClass':
        soql = 'SELECT Name, LastModifiedDate FROM ApexClass ORDER BY Name'
        result = sf.query(soql)
        for r in result.get('records', []):
            name = r.get('Name', '')
            components.append({
                'member': name,
                'type': 'ApexClass',
                'label': name,
            })

    elif component_type == 'ApexTrigger':
        soql = 'SELECT Name, TableEnumOrId FROM ApexTrigger ORDER BY Name'
        result = sf.query(soql)
        for r in result.get('records', []):
            name = r.get('Name', '')
            obj = r.get('TableEnumOrId', '')
            label = f'{name} (on {obj})' if obj else name
            components.append({
                'member': name,
                'type': 'ApexTrigger',
                'label': label,
            })

    elif component_type == 'Flow':
        soql = (
            'SELECT DeveloperName, MasterLabel, ProcessType, Status '
            'FROM FlowDefinition ORDER BY MasterLabel'
        )
        try:
            result = sf.query(soql)
        except Exception:
            # Fallback: some orgs expose FlowDefinition only via Tooling API
            logger.info('FlowDefinition standard query failed — trying Tooling API')
            result = sf.restful('tooling/query/', params={'q': soql})
        for r in result.get('records', []):
            dev_name = r.get('DeveloperName', '')
            label = r.get('MasterLabel', dev_name)
            process_type = r.get('ProcessType', '')
            status = r.get('Status', '')
            display = label
            if process_type:
                display = f'{label} ({process_type})'
            if status and status.lower() != 'active':
                display = f'{display} [{status}]'
            components.append({
                'member': dev_name,
                'type': 'Flow',
                'label': display,
            })

    elif component_type == 'PermissionSet':
        soql = (
            'SELECT Name, Label FROM PermissionSet '
            'WHERE IsOwnedByProfile = false ORDER BY Label'
        )
        result = sf.query(soql)
        for r in result.get('records', []):
            name = r.get('Name', '')
            label = r.get('Label', name)
            components.append({
                'member': name,
                'type': 'PermissionSet',
                'label': label,
            })

    elif component_type == 'CustomField':
        soql = (
            'SELECT DeveloperName, EntityDefinition.QualifiedApiName, Label '
            'FROM CustomField WHERE ManageableState = \'unmanaged\' '
            'ORDER BY EntityDefinition.QualifiedApiName, DeveloperName '
            'LIMIT 500'
        )
        result = sf.restful('tooling/query/', params={'q': soql})
        for r in result.get('records', []):
            dev_name = r.get('DeveloperName', '')
            entity = r.get('EntityDefinition') or {}
            obj_name = entity.get('QualifiedApiName', '')
            field_label = r.get('Label', dev_name)
            member = f'{obj_name}.{dev_name}__c'
            label = f'{member} — {field_label}' if field_label else member
            components.append({
                'member': member,
                'type': 'CustomField',
                'label': label,
            })

    elif component_type == 'ValidationRule':
        soql = (
            'SELECT ValidationName, EntityDefinition.QualifiedApiName '
            'FROM ValidationRule '
            'ORDER BY EntityDefinition.QualifiedApiName, ValidationName '
            'LIMIT 500'
        )
        result = sf.restful('tooling/query/', params={'q': soql})
        for r in result.get('records', []):
            rule_name = r.get('ValidationName', '')
            entity = r.get('EntityDefinition') or {}
            obj_name = entity.get('QualifiedApiName', '')
            member = f'{obj_name}.{rule_name}'
            components.append({
                'member': member,
                'type': 'ValidationRule',
                'label': member,
            })

    else:
        logger.warning('list_components: unsupported type %s', component_type)

    return components


def build_package(components: list, api_version: str = '65.0') -> dict:
    """Build a package.xml string and a deployment checklist from selected components.

    Args:
        components: List of dicts with keys ``type`` and ``member``.
        api_version: Salesforce API version string, e.g. ``'65.0'``.

    Returns:
        Dict with keys:
          - ``package_xml``: rendered XML string
          - ``checklist``: list of dicts ``{type_label, type_name, members: [str]}``
    """
    # Group members by type, preserving a stable ordering
    _ORDER = ['ApexClass', 'ApexTrigger', 'CustomField', 'Flow', 'PermissionSet', 'ValidationRule']
    by_type: dict = {t: [] for t in _ORDER}

    for comp in components:
        t = comp.get('type', '')
        m = comp.get('member', '')
        if not t or not m:
            continue
        if t not in by_type:
            by_type[t] = []
        if m not in by_type[t]:
            by_type[t].append(m)

    # Sort members within each type
    for t in by_type:
        by_type[t].sort()

    # Build XML
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Package xmlns="http://soap.sforce.com/2006/04/metadata">',
    ]
    for type_name in _ORDER:
        members = by_type.get(type_name, [])
        if not members:
            continue
        lines.append('    <types>')
        for m in members:
            lines.append(f'        <members>{xml_escape(m)}</members>')
        lines.append(f'        <name>{xml_escape(type_name)}</name>')
        lines.append('    </types>')
    lines.append(f'    <version>{xml_escape(api_version)}</version>')
    lines.append('</Package>')
    package_xml = '\n'.join(lines)

    # Build checklist
    checklist = []
    for type_name in _ORDER:
        members = by_type.get(type_name, [])
        if not members:
            continue
        checklist.append({
            'type_label': _TYPE_LABELS.get(type_name, type_name),
            'type_name': type_name,
            'members': [
                {
                    'member': m,
                    'setup_path': _setup_path(type_name, m),
                }
                for m in members
            ],
        })

    return {
        'package_xml': package_xml,
        'checklist': checklist,
    }
