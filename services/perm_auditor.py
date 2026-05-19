import logging
from collections import defaultdict

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def get_assignments(org: str) -> list:
    sf = get_sf(org)
    soql = (
        "SELECT Id, PermissionSet.Name, PermissionSet.Label, PermissionSet.IsOwnedByProfile, "
        "Assignee.Name, Assignee.Username "
        "FROM PermissionSetAssignment "
        "WHERE PermissionSet.IsOwnedByProfile = false "
        "ORDER BY PermissionSet.Name "
        "LIMIT 500"
    )
    res = sf.query_all(soql)
    return res.get('records', [])


def get_field_access(org: str, object_name: str) -> dict:
    sf = get_sf(org)
    soql = (
        f"SELECT Id, SobjectType, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions "
        f"WHERE SobjectType = '{object_name}' "
        f"ORDER BY Field "
        f"LIMIT 500"
    )
    res = sf.query_all(soql)
    records = res.get('records', [])

    grouped: dict = defaultdict(lambda: {'read_psets': [], 'edit_psets': []})
    for rec in records:
        field = rec.get('Field', '')
        if rec.get('PermissionsRead'):
            grouped[field]['read_psets'].append(rec.get('Id', ''))
        if rec.get('PermissionsEdit'):
            grouped[field]['edit_psets'].append(rec.get('Id', ''))

    return {
        'object_name': object_name,
        'permissions': dict(grouped),
        'raw_records': records,
    }


def summarize_field(org: str, object_name: str, field_api_name: str) -> dict:
    sf = get_sf(org)

    # Field permissions for the specific field
    fp_soql = (
        f"SELECT Id, SobjectType, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions "
        f"WHERE SobjectType = '{object_name}' "
        f"ORDER BY Field "
        f"LIMIT 500"
    )
    fp_res = sf.query_all(fp_soql)
    fp_records = fp_res.get('records', [])

    # Filter to the target field (API name may be prefixed with object name)
    target_variants = {field_api_name.lower(), f"{object_name.lower()}.{field_api_name.lower()}"}
    relevant = [
        r for r in fp_records
        if (r.get('Field', '') or '').lower() in target_variants
    ]

    # Permission set assignments
    assign_soql = (
        "SELECT Id, PermissionSet.Name, PermissionSet.Label, PermissionSet.IsOwnedByProfile, "
        "Assignee.Name, Assignee.Username "
        "FROM PermissionSetAssignment "
        "WHERE PermissionSet.IsOwnedByProfile = false "
        "ORDER BY PermissionSet.Name "
        "LIMIT 500"
    )
    assign_res = sf.query_all(assign_soql)
    assignments = assign_res.get('records', [])

    # Build pset_id → list of users map
    pset_users: dict = defaultdict(list)
    for a in assignments:
        ps = a.get('PermissionSet') or {}
        pset_name = ps.get('Name', '')
        assignee = a.get('Assignee') or {}
        pset_users[pset_name].append({
            'name': assignee.get('Name', ''),
            'username': assignee.get('Username', ''),
        })

    rows = []
    for rec in relevant:
        ps_id = rec.get('Id', '')
        ps_label = rec.get('Field', field_api_name)
        rows.append({
            'pset_id': ps_id,
            'pset_name': ps_label,
            'can_read': rec.get('PermissionsRead', False),
            'can_edit': rec.get('PermissionsEdit', False),
            'users': pset_users.get(ps_id, []),
        })

    return {
        'object_name': object_name,
        'field_api_name': field_api_name,
        'access': rows,
    }
