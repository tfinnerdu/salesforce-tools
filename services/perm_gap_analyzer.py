"""Compare two Permission Sets to find access gaps."""
import logging
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_OBJECT_PERM_COLS = ['PermissionsRead', 'PermissionsCreate', 'PermissionsEdit',
                     'PermissionsDelete', 'PermissionsViewAllRecords', 'PermissionsModifyAllRecords']
_PERM_LABELS = {
    'PermissionsRead': 'Read',
    'PermissionsCreate': 'Create',
    'PermissionsEdit': 'Edit',
    'PermissionsDelete': 'Delete',
    'PermissionsViewAllRecords': 'ViewAllRecords',
    'PermissionsModifyAllRecords': 'ModifyAllRecords',
}


def list_permission_sets(org: str) -> list:
    """Return all non-Profile permission sets for the picker."""
    sf = get_sf(org)
    soql = (
        "SELECT Id, Name, Label, Description, IsCustom "
        "FROM PermissionSet WHERE IsOwnedByProfile = false "
        "ORDER BY Label"
    )
    try:
        result = sf.query(soql)
        perm_sets = [
            {
                'id': r['Id'],
                'name': r.get('Name', ''),
                'label': r.get('Label', ''),
                'description': r.get('Description') or '',
            }
            for r in result.get('records', [])
        ]
        return perm_sets
    except Exception:
        raise


def compare(org: str, ps_id_a: str, ps_id_b: str) -> dict:
    """
    Compare object permissions and field permissions between two permission sets.

    Returns {
        ps_a: {id, label},
        ps_b: {id, label},
        object_gaps: list of {object, permission, in_a, in_b},
        field_gaps: list of {object, field, permission, in_a, in_b},
        summary: {only_in_a, only_in_b, shared_objects, total_gaps}
    }
    """
    sf = get_sf(org)

    try:
        # Resolve labels
        label_soql = (
            f"SELECT Id, Label FROM PermissionSet "
            f"WHERE Id IN ('{ps_id_a}', '{ps_id_b}')"
        )
        label_res = sf.query(label_soql)
        labels = {r['Id']: r.get('Label', r['Id']) for r in label_res.get('records', [])}
        label_a = labels.get(ps_id_a, ps_id_a)
        label_b = labels.get(ps_id_b, ps_id_b)

        # Object permissions
        obj_soql = (
            f"SELECT SobjectType, PermissionsRead, PermissionsCreate, PermissionsEdit, "
            f"PermissionsDelete, PermissionsViewAllRecords, PermissionsModifyAllRecords, ParentId "
            f"FROM ObjectPermissions "
            f"WHERE ParentId IN ('{ps_id_a}', '{ps_id_b}')"
        )
        obj_res = sf.query_all(obj_soql)
        obj_gaps = _build_object_gaps(obj_res.get('records', []), ps_id_a, ps_id_b)

        # Field permissions
        field_soql = (
            f"SELECT SobjectType, Field, PermissionsRead, PermissionsEdit, ParentId "
            f"FROM FieldPermissions "
            f"WHERE ParentId IN ('{ps_id_a}', '{ps_id_b}')"
        )
        field_res = sf.query_all(field_soql)
        field_gaps = _build_field_gaps(field_res.get('records', []), ps_id_a, ps_id_b)

    except Exception:
        raise

    only_in_a = sum(1 for g in obj_gaps + field_gaps if g['in_a'] and not g['in_b'])
    only_in_b = sum(1 for g in obj_gaps + field_gaps if g['in_b'] and not g['in_a'])
    total_gaps = len(obj_gaps) + len(field_gaps)

    # Count shared objects (appear in both PS obj perm sets)
    obj_records = sf.query(obj_soql).get('records', []) if False else []
    shared_objects = 0  # computed below via the data we already built

    # Recompute shared_objects from what we queried
    obj_a_set: set = set()
    obj_b_set: set = set()
    try:
        for r in sf.query_all(
            f"SELECT SobjectType, ParentId FROM ObjectPermissions "
            f"WHERE ParentId IN ('{ps_id_a}', '{ps_id_b}')"
        ).get('records', []):
            if r.get('ParentId') == ps_id_a:
                obj_a_set.add(r['SobjectType'])
            elif r.get('ParentId') == ps_id_b:
                obj_b_set.add(r['SobjectType'])
        shared_objects = len(obj_a_set & obj_b_set)
    except Exception:
        shared_objects = 0

    return {
        'ps_a': {'id': ps_id_a, 'label': label_a},
        'ps_b': {'id': ps_id_b, 'label': label_b},
        'object_gaps': obj_gaps,
        'field_gaps': field_gaps,
        'summary': {
            'only_in_a': only_in_a,
            'only_in_b': only_in_b,
            'shared_objects': shared_objects,
            'total_gaps': total_gaps,
        },
    }


def _build_object_gaps(records: list, ps_id_a: str, ps_id_b: str) -> list:
    """Build gap list from ObjectPermissions records."""
    # {sobject: {col: bool}} for each PS
    perms_a: dict = {}
    perms_b: dict = {}

    for rec in records:
        sobj = rec.get('SobjectType', '')
        parent = rec.get('ParentId', '')
        target = perms_a if parent == ps_id_a else (perms_b if parent == ps_id_b else None)
        if target is None:
            continue
        target[sobj] = {col: bool(rec.get(col, False)) for col in _OBJECT_PERM_COLS}

    gaps = []
    all_objects = set(perms_a) | set(perms_b)
    for sobj in sorted(all_objects):
        a_perms = perms_a.get(sobj, {})
        b_perms = perms_b.get(sobj, {})
        for col in _OBJECT_PERM_COLS:
            a_val = a_perms.get(col, False)
            b_val = b_perms.get(col, False)
            if a_val != b_val:
                gaps.append({
                    'object': sobj,
                    'permission': _PERM_LABELS.get(col, col),
                    'in_a': a_val,
                    'in_b': b_val,
                })
    return gaps


def _build_field_gaps(records: list, ps_id_a: str, ps_id_b: str) -> list:
    """Build gap list from FieldPermissions records."""
    # {(sobject, field): {col: bool}} for each PS
    perms_a: dict = {}
    perms_b: dict = {}

    for rec in records:
        sobj = rec.get('SobjectType', '')
        field = rec.get('Field', '')
        parent = rec.get('ParentId', '')
        key = (sobj, field)
        target = perms_a if parent == ps_id_a else (perms_b if parent == ps_id_b else None)
        if target is None:
            continue
        target[key] = {
            'PermissionsRead': bool(rec.get('PermissionsRead', False)),
            'PermissionsEdit': bool(rec.get('PermissionsEdit', False)),
        }

    gaps = []
    all_keys = set(perms_a) | set(perms_b)
    for (sobj, field) in sorted(all_keys):
        a_perms = perms_a.get((sobj, field), {})
        b_perms = perms_b.get((sobj, field), {})
        for col, label in [('PermissionsRead', 'Read'), ('PermissionsEdit', 'Edit')]:
            a_val = a_perms.get(col, False)
            b_val = b_perms.get(col, False)
            if a_val != b_val:
                gaps.append({
                    'object': sobj,
                    'field': field,
                    'permission': label,
                    'in_a': a_val,
                    'in_b': b_val,
                })
    return gaps
