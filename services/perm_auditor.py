import logging
from collections import defaultdict

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)


# ── Permission Sets ───────────────────────────────────────────────────────────

def get_permission_sets(org: str) -> list:
    """List all custom permission sets with user assignment counts."""
    sf = get_sf(org)
    soql = (
        "SELECT Id, Name, Label, Description, IsCustom, Type, NamespacePrefix "
        "FROM PermissionSet "
        "WHERE IsOwnedByProfile = false "
        "ORDER BY Label"
    )
    res = sf.query_all(soql)
    psets = res.get('records', [])

    # Count assignments per perm set
    assign_soql = (
        "SELECT PermissionSetId, COUNT(Id) cnt "
        "FROM PermissionSetAssignment "
        "WHERE PermissionSet.IsOwnedByProfile = false "
        "GROUP BY PermissionSetId"
    )
    try:
        assign_res = sf.query_all(assign_soql)
        counts = {r['PermissionSetId']: r['cnt'] for r in assign_res.get('records', [])}
    except Exception:
        counts = {}

    result = []
    for p in psets:
        result.append({
            'id': p.get('Id'),
            'name': p.get('Name', ''),
            'label': p.get('Label', ''),
            'description': p.get('Description', '') or '',
            'is_custom': bool(p.get('IsCustom', False)),
            'type': p.get('Type', ''),
            'namespace': p.get('NamespacePrefix', '') or '',
            'user_count': counts.get(p.get('Id'), 0),
        })
    return result


# ── Users ─────────────────────────────────────────────────────────────────────

def get_users(org: str, search: str = '') -> list:
    """List active users with profile names."""
    sf = get_sf(org)
    where_parts = ["IsActive = true"]
    if search:
        safe = search.replace("'", "\\'")
        where_parts.append(f"(Name LIKE '%{safe}%' OR Username LIKE '%{safe}%')")
    where = ' AND '.join(where_parts)
    soql = (
        f"SELECT Id, Name, Username, Email, IsActive, Profile.Id, Profile.Name, "
        f"LastLoginDate, CreatedDate "
        f"FROM User WHERE {where} ORDER BY Name LIMIT 200"
    )
    res = sf.query_all(soql)
    users = []
    for r in res.get('records', []):
        profile = r.get('Profile') or {}
        users.append({
            'id': r.get('Id'),
            'name': r.get('Name', ''),
            'username': r.get('Username', ''),
            'email': r.get('Email', '') or '',
            'profile_id': profile.get('Id', ''),
            'profile_name': profile.get('Name', ''),
            'last_login': r.get('LastLoginDate'),
            'created_date': r.get('CreatedDate'),
        })
    return users


def get_user_detail(org: str, user_id: str) -> dict:
    """Full permission picture for a single user: profile + perm sets + object access."""
    sf = get_sf(org)

    # User basics + profile
    user_soql = (
        f"SELECT Id, Name, Username, Email, IsActive, Profile.Id, Profile.Name, "
        f"Profile.UserLicense.Name, LastLoginDate "
        f"FROM User WHERE Id = '{user_id}' LIMIT 1"
    )
    user_res = sf.query(user_soql)
    user_records = user_res.get('records', [])
    if not user_records:
        return {}
    u = user_records[0]
    profile = u.get('Profile') or {}
    license_info = profile.get('UserLicense') or {}

    # Assigned permission sets
    assign_soql = (
        f"SELECT PermissionSet.Id, PermissionSet.Name, PermissionSet.Label, "
        f"PermissionSet.Description "
        f"FROM PermissionSetAssignment "
        f"WHERE AssigneeId = '{user_id}' "
        f"AND PermissionSet.IsOwnedByProfile = false "
        f"ORDER BY PermissionSet.Label"
    )
    assign_res = sf.query_all(assign_soql)
    psets = []
    pset_ids = []
    for a in assign_res.get('records', []):
        ps = a.get('PermissionSet') or {}
        psets.append({
            'id': ps.get('Id', ''),
            'name': ps.get('Name', ''),
            'label': ps.get('Label', ''),
            'description': ps.get('Description', '') or '',
        })
        if ps.get('Id'):
            pset_ids.append(ps['Id'])

    # Aggregate object permissions across all perm sets for this user
    obj_perms = {}
    if pset_ids:
        id_list = "', '".join(pset_ids)
        obj_soql = (
            f"SELECT SobjectType, PermissionsRead, PermissionsCreate, PermissionsEdit, "
            f"PermissionsDelete, PermissionsViewAllRecords, PermissionsModifyAllRecords "
            f"FROM ObjectPermissions "
            f"WHERE ParentId IN ('{id_list}') "
            f"ORDER BY SobjectType"
        )
        try:
            obj_res = sf.query_all(obj_soql)
            for r in obj_res.get('records', []):
                obj = r.get('SobjectType', '')
                if obj not in obj_perms:
                    obj_perms[obj] = {
                        'read': False, 'create': False, 'edit': False,
                        'delete': False, 'view_all': False, 'modify_all': False,
                    }
                if r.get('PermissionsRead'):    obj_perms[obj]['read'] = True
                if r.get('PermissionsCreate'):  obj_perms[obj]['create'] = True
                if r.get('PermissionsEdit'):    obj_perms[obj]['edit'] = True
                if r.get('PermissionsDelete'):  obj_perms[obj]['delete'] = True
                if r.get('PermissionsViewAllRecords'):   obj_perms[obj]['view_all'] = True
                if r.get('PermissionsModifyAllRecords'): obj_perms[obj]['modify_all'] = True
        except Exception as exc:
            logger.warning('obj perms query failed: %s', exc)

    obj_list = [{'object': k, **v} for k, v in sorted(obj_perms.items())]

    return {
        'id': u.get('Id'),
        'name': u.get('Name', ''),
        'username': u.get('Username', ''),
        'email': u.get('Email', '') or '',
        'profile_id': profile.get('Id', ''),
        'profile_name': profile.get('Name', ''),
        'license': license_info.get('Name', ''),
        'last_login': u.get('LastLoginDate'),
        'permission_sets': psets,
        'object_permissions': obj_list,
    }


# ── Permission Set Detail ─────────────────────────────────────────────────────

def get_pset_detail(org: str, pset_id: str) -> dict:
    """Full detail for a permission set: label, users, object perms, field perms."""
    sf = get_sf(org)

    # Perm set metadata
    ps_soql = (
        f"SELECT Id, Name, Label, Description, IsCustom, Type "
        f"FROM PermissionSet WHERE Id = '{pset_id}' LIMIT 1"
    )
    ps_res = sf.query(ps_soql)
    ps_records = ps_res.get('records', [])
    if not ps_records:
        return {}
    ps = ps_records[0]

    # Assigned users
    assign_soql = (
        f"SELECT Assignee.Id, Assignee.Name, Assignee.Username "
        f"FROM PermissionSetAssignment "
        f"WHERE PermissionSetId = '{pset_id}' "
        f"ORDER BY Assignee.Name LIMIT 200"
    )
    assign_res = sf.query_all(assign_soql)
    users = []
    for a in assign_res.get('records', []):
        assignee = a.get('Assignee') or {}
        users.append({
            'id': assignee.get('Id', ''),
            'name': assignee.get('Name', ''),
            'username': assignee.get('Username', ''),
        })

    # Object permissions
    obj_soql = (
        f"SELECT SobjectType, PermissionsRead, PermissionsCreate, PermissionsEdit, "
        f"PermissionsDelete, PermissionsViewAllRecords, PermissionsModifyAllRecords "
        f"FROM ObjectPermissions WHERE ParentId = '{pset_id}' ORDER BY SobjectType"
    )
    obj_res = sf.query_all(obj_soql)
    obj_perms = [
        {
            'object': r.get('SobjectType', ''),
            'read': bool(r.get('PermissionsRead')),
            'create': bool(r.get('PermissionsCreate')),
            'edit': bool(r.get('PermissionsEdit')),
            'delete': bool(r.get('PermissionsDelete')),
            'view_all': bool(r.get('PermissionsViewAllRecords')),
            'modify_all': bool(r.get('PermissionsModifyAllRecords')),
        }
        for r in obj_res.get('records', [])
    ]

    # Field permissions (top 200 — grouped by object)
    field_soql = (
        f"SELECT SobjectType, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions WHERE ParentId = '{pset_id}' "
        f"ORDER BY SobjectType, Field LIMIT 500"
    )
    field_res = sf.query_all(field_soql)
    field_perms = [
        {
            'object': r.get('SobjectType', ''),
            'field': r.get('Field', ''),
            'read': bool(r.get('PermissionsRead')),
            'edit': bool(r.get('PermissionsEdit')),
        }
        for r in field_res.get('records', [])
    ]

    return {
        'id': ps.get('Id'),
        'name': ps.get('Name', ''),
        'label': ps.get('Label', ''),
        'description': ps.get('Description', '') or '',
        'is_custom': bool(ps.get('IsCustom', False)),
        'type': ps.get('Type', ''),
        'users': users,
        'object_permissions': obj_perms,
        'field_permissions': field_perms,
    }


# ── Object Permission Matrix ──────────────────────────────────────────────────

def get_object_access_matrix(org: str, object_name: str) -> dict:
    """For a given SF object, show which perm sets grant access and what CRUD they allow."""
    sf = get_sf(org)
    soql = (
        f"SELECT Parent.Id, Parent.Name, Parent.Label, "
        f"PermissionsRead, PermissionsCreate, PermissionsEdit, "
        f"PermissionsDelete, PermissionsViewAllRecords, PermissionsModifyAllRecords "
        f"FROM ObjectPermissions "
        f"WHERE SobjectType = '{object_name}' "
        f"AND Parent.IsOwnedByProfile = false "
        f"ORDER BY Parent.Label"
    )
    res = sf.query_all(soql)
    rows = []
    for r in res.get('records', []):
        parent = r.get('Parent') or {}
        rows.append({
            'pset_id': parent.get('Id', ''),
            'pset_name': parent.get('Name', ''),
            'pset_label': parent.get('Label', ''),
            'read': bool(r.get('PermissionsRead')),
            'create': bool(r.get('PermissionsCreate')),
            'edit': bool(r.get('PermissionsEdit')),
            'delete': bool(r.get('PermissionsDelete')),
            'view_all': bool(r.get('PermissionsViewAllRecords')),
            'modify_all': bool(r.get('PermissionsModifyAllRecords')),
        })
    return {'object_name': object_name, 'rows': rows}


def get_field_access_matrix(org: str, object_name: str) -> dict:
    """For a given SF object, show field-by-field read/edit access across all perm sets."""
    sf = get_sf(org)
    soql = (
        f"SELECT Parent.Id, Parent.Name, Parent.Label, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions "
        f"WHERE SobjectType = '{object_name}' "
        f"AND Parent.IsOwnedByProfile = false "
        f"ORDER BY Field, Parent.Label LIMIT 1000"
    )
    res = sf.query_all(soql)

    # Group by field
    fields: dict = defaultdict(list)
    for r in res.get('records', []):
        parent = r.get('Parent') or {}
        field = r.get('Field', '').split('.')[-1]  # strip object prefix if present
        fields[field].append({
            'pset_id': parent.get('Id', ''),
            'pset_label': parent.get('Label', ''),
            'read': bool(r.get('PermissionsRead')),
            'edit': bool(r.get('PermissionsEdit')),
        })

    return {
        'object_name': object_name,
        'fields': [{'field': f, 'access': a} for f, a in sorted(fields.items())],
    }


# ── Legacy helpers (kept for backward compat) ─────────────────────────────────

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
    return {'object_name': object_name, 'permissions': dict(grouped), 'raw_records': records}
