"""CLI tab — mirror a source org's object + field access onto same-named
profiles and permission sets in the target.

When a custom object is cloned EDA -> Ed Cloud, its fields land hidden. The
Visibility section clones ONE reference field's FLS into a fresh permission set;
this goes further: it reads *every* profile and permission set that grants
access to the object in a **source** org (e.g. EDA) and generates ADDITIVE grant
files for the same-named profiles/permission sets that already exist in the
**target** — so the object's security posture is reproduced *by name*, not
rebuilt by hand. Source parents with no same-named twin in the target are
reported (never invented).

Read-only against Salesforce. A partial Profile / PermissionSet deploy is
additive for objectPermissions / fieldPermissions (Salesforce upserts the
referenced permissions and leaves the rest of the profile/permission set
untouched), so the generated files are safe to deploy onto existing metadata.

Field grants are scoped to the fields that will actually exist in the target
(the ones being cloned now, plus any already present), so a mirrored file never
references a field the target lacks — which would fail the whole deploy.
"""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _soql_escape(value: str) -> str:
    """Escape a value for embedding inside a single-quoted SOQL literal."""
    return (value or '').replace('\\', '\\\\').replace("'", "\\'")


def _parent_of(rec: dict):
    """(type, name) for a FieldPermissions/ObjectPermissions row's Parent, or None.

    A profile-owned permission set represents its profile (use Parent.Profile.Name,
    since its own Name is an opaque `X00e...`); a real permission set uses
    Parent.Name (its API name — the metadata fullName + target match key).
    """
    parent = rec.get('Parent') or {}
    if parent.get('IsOwnedByProfile'):
        name = (parent.get('Profile') or {}).get('Name')
        return ('Profile', name) if name else None
    name = parent.get('Name')
    return ('PermissionSet', name) if name else None


def read_object_access_from(sf, object_name: str) -> dict:
    """Read object + field access for `object_name`, grouped by parent.

    Returns {object, parents:[{name, type, object_perms|None, field_perms:[...]}]}
    where object_perms is {read,create,edit,delete,view_all,modify_all} and each
    field_perm is {field:'Obj.Field__c', readable, editable}. Only parents that
    actually grant something (object read, or a readable/editable field) appear.
    """
    object_name = (object_name or '').strip()
    esc = _soql_escape(object_name)
    parents = {}   # (type,name) -> entry

    def _entry(key):
        if key not in parents:
            parents[key] = {'name': key[1], 'type': key[0],
                            'object_perms': None, 'field_perms': {}}
        return parents[key]

    op_soql = (
        "SELECT Parent.Name, Parent.Profile.Name, Parent.IsOwnedByProfile, "
        "PermissionsCreate, PermissionsRead, PermissionsEdit, PermissionsDelete, "
        "PermissionsViewAllRecords, PermissionsModifyAllRecords "
        "FROM ObjectPermissions "
        f"WHERE SobjectType = '{esc}'"
    )
    for r in sf.query_all(op_soql).get('records', []):
        key = _parent_of(r)
        if not key:
            continue
        read = bool(r.get('PermissionsRead'))
        create = bool(r.get('PermissionsCreate'))
        edit = bool(r.get('PermissionsEdit'))
        delete = bool(r.get('PermissionsDelete'))
        view_all = bool(r.get('PermissionsViewAllRecords'))
        modify_all = bool(r.get('PermissionsModifyAllRecords'))
        if not (read or create or edit or delete or view_all or modify_all):
            continue
        _entry(key)['object_perms'] = {
            'object': object_name,
            'read': read, 'create': create, 'edit': edit, 'delete': delete,
            'view_all': view_all, 'modify_all': modify_all,
        }

    fp_soql = (
        "SELECT Field, Parent.Name, Parent.Profile.Name, Parent.IsOwnedByProfile, "
        "PermissionsRead, PermissionsEdit "
        "FROM FieldPermissions "
        f"WHERE SobjectType = '{esc}'"
    )
    for r in sf.query_all(fp_soql).get('records', []):
        key = _parent_of(r)
        field = r.get('Field')
        if not key or not field:
            continue
        readable = bool(r.get('PermissionsRead'))
        editable = bool(r.get('PermissionsEdit'))
        if not (readable or editable):
            continue
        _entry(key)['field_perms'][field] = {
            'field': field, 'readable': readable, 'editable': editable,
        }

    out = []
    for entry in parents.values():
        # Drop parents that ended up granting nothing.
        if not entry['object_perms'] and not entry['field_perms']:
            continue
        entry_fps = sorted(entry['field_perms'].values(), key=lambda fp: fp['field'].lower())
        out.append({'name': entry['name'], 'type': entry['type'],
                    'object_perms': entry['object_perms'], 'field_perms': entry_fps})
    out.sort(key=lambda e: (e['type'], e['name'].lower()))
    return {'object': object_name, 'parents': out}


def read_object_access(source_org: str, object_name: str) -> dict:
    """read_object_access_from over a live source-org client."""
    return read_object_access_from(get_sf(source_org), object_name)


def target_catalog(sf) -> dict:
    """Names present in the target: profiles (set) + permission sets (name->label).

    Real (assignable) permission sets only — profile-owned ones (the `X00e...`)
    are excluded; those are represented by their profile.
    """
    profiles = set()
    for r in sf.query_all("SELECT Name FROM Profile").get('records', []):
        if r.get('Name'):
            profiles.add(r['Name'])
    permission_sets = {}
    for r in sf.query_all(
            "SELECT Name, Label FROM PermissionSet WHERE IsOwnedByProfile = false"
    ).get('records', []):
        if r.get('Name'):
            permission_sets[r['Name']] = r.get('Label') or r['Name']
    return {'profiles': profiles, 'permission_sets': permission_sets}


def target_field_set(sf, object_name: str):
    """`Object.Field` API names that already exist in the target for object_name,
    or None if the object itself isn't there yet (it'll be created by the same
    deploy, so there's nothing existing to scope against)."""
    try:
        desc = sf.restful(f'sobjects/{object_name}/describe') or {}
    except Exception:
        return None
    return {f'{object_name}.{f.get("name")}' for f in (desc.get('fields') or [])
            if f.get('name')}


def mirror_plan(source_org: str, target_org: str, object_name: str,
                cloned_fields=None) -> dict:
    """Full mirror plan for one object.

    Reads the source org's per-parent access, checks each parent name against the
    target's profiles / permission sets, and scopes field grants to fields that
    will exist in the target (cloned_fields ∪ fields already present). Returns:

      {object, source_org, target_org, target_object_exists, scoped,
       matched:[{name, type, object_perms, field_perms, dropped_fields}],
       unmatched:[{name, type}], counts:{...}}

    cloned_fields: `Object.Field` API names being deployed now (from the clone
    plan). Combined with the target's existing fields to form the allow-list.
    """
    object_name = (object_name or '').strip()
    if not object_name:
        raise ValueError('object is required')

    source = read_object_access(source_org, object_name)
    tgt = get_sf(target_org)
    catalog = target_catalog(tgt)
    existing = target_field_set(tgt, object_name)
    target_object_exists = existing is not None

    allowed = {f for f in (cloned_fields or []) if f}
    if existing:
        allowed |= existing
    scoped = bool(allowed)

    matched, unmatched = [], []
    for p in source['parents']:
        present = (p['name'] in catalog['profiles']) if p['type'] == 'Profile' \
            else (p['name'] in catalog['permission_sets'])
        if not present:
            unmatched.append({'name': p['name'], 'type': p['type']})
            continue
        if scoped:
            kept = [fp for fp in p['field_perms'] if fp['field'] in allowed]
            dropped = len(p['field_perms']) - len(kept)
        else:
            kept, dropped = p['field_perms'], 0
        entry = {'name': p['name'], 'type': p['type'],
                 'object_perms': p['object_perms'], 'field_perms': kept,
                 'dropped_fields': dropped}
        if p['type'] == 'PermissionSet':
            entry['label'] = catalog['permission_sets'].get(p['name'], p['name'])
        matched.append(entry)

    matched_profiles = [m for m in matched if m['type'] == 'Profile']
    matched_permsets = [m for m in matched if m['type'] == 'PermissionSet']
    return {
        'object': object_name,
        'source_org': source_org,
        'target_org': target_org,
        'target_object_exists': target_object_exists,
        'scoped': scoped,
        'matched': matched,
        'unmatched': unmatched,
        'counts': {
            'source_parents': len(source['parents']),
            'matched': len(matched),
            'matched_profiles': len(matched_profiles),
            'matched_permsets': len(matched_permsets),
            'unmatched': len(unmatched),
        },
    }


def split_grants(matched: list) -> tuple:
    """Turn matched parents into (profiles, permsets) specs for build_package_zip.

    profiles: [{api_name, object_perms:[...], field_perms:[...], description}]
    permsets: [{api_name, label, object_perms:[...], field_perms:[...], description}]
    Object perms are wrapped in a list (the generators take a list).
    """
    profiles, permsets = [], []
    for m in matched:
        ops = [m['object_perms']] if m.get('object_perms') else []
        fps = m.get('field_perms') or []
        if m['type'] == 'Profile':
            profiles.append({
                'api_name': m['name'],
                'object_perms': ops,
                'field_perms': fps,
                'description': f'Mirrored access for {m["name"]} (name-matched).',
            })
        else:
            permsets.append({
                'api_name': m['name'],
                'label': m.get('label') or m['name'],
                'object_perms': ops,
                'field_perms': fps,
                'description': '',
            })
    return profiles, permsets
