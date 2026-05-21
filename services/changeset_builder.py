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
        # FlowDefinitionView (Data API) exposes ProcessType + IsActive;
        # FlowDefinition (Tooling) has neither column.
        soql = (
            'SELECT ApiName, Label, ProcessType, IsActive '
            'FROM FlowDefinitionView ORDER BY Label'
        )
        result = sf.query(soql)
        for r in result.get('records', []):
            api_name = r.get('ApiName', '')
            label = r.get('Label', api_name)
            process_type = r.get('ProcessType', '')
            display = f'{label} ({process_type})' if process_type else label
            if not r.get('IsActive'):
                display = f'{display} [Inactive]'
            components.append({
                'member': api_name,
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
        # CustomField has no 'Label' column (it lives in Metadata). Ordering
        # by a cross-entity relationship can also choke the Tooling API, so
        # the result is sorted in Python instead.
        soql = (
            'SELECT DeveloperName, EntityDefinition.QualifiedApiName '
            'FROM CustomField WHERE ManageableState = \'unmanaged\' '
            'LIMIT 2000'
        )
        result = sf.restful('tooling/query/', params={'q': soql})
        for r in result.get('records', []):
            dev_name = r.get('DeveloperName', '')
            entity = r.get('EntityDefinition') or {}
            obj_name = entity.get('QualifiedApiName', '')
            member = f'{obj_name}.{dev_name}__c'
            components.append({
                'member': member,
                'type': 'CustomField',
                'label': member,
            })

    elif component_type == 'ValidationRule':
        # The Tooling API cannot ORDER BY a cross-entity relationship over
        # every ValidationRule (UNKNOWN_EXCEPTION) — sort in Python.
        soql = (
            'SELECT ValidationName, EntityDefinition.QualifiedApiName '
            'FROM ValidationRule LIMIT 2000'
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

    components.sort(key=lambda c: c['member'])
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
