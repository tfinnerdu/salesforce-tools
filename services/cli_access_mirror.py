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

from services import audit
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _soql_escape(value: str) -> str:
    """Escape a value for embedding inside a single-quoted SOQL literal."""
    return (value or '').replace('\\', '\\\\').replace("'", "\\'")


# Profiles that reliably reject even a minimal, additive deploy because a
# license-locked field permission conflicts during validation ("You may not turn
# off permission Read X for this License Type"). Kept deliberately NARROW and
# evidence-based: most integration/standard profiles (Analytics Cloud, CPQ, Sales
# Insights, SalesforceIQ, Salesforce API Only, …) DO deploy additively, so
# skipping them by name would wrongly drop grants the user wants. B2BMA
# Integration User is the notorious exception (its B2B Marketing Analytics license
# locks a managed field), so it's the only default. Add a name here only after a
# real deploy proves it can't take an additive profile change. Reported as
# `skipped_locked`, never silently dropped.
LOCKED_PROFILES = frozenset({
    'B2BMA Integration User',
})


def _is_locked_profile(name: str) -> bool:
    return name in LOCKED_PROFILES


# Profiles whose access is high-consequence to replicate cross-org (System
# Administrator and equivalents). Distinct from LOCKED_PROFILES — this is a
# governance gate, not a deploy-mechanics one. Excluded from a mirror by
# default; the caller must explicitly opt in (include_high_privilege=True) to
# include them, and they are always reported either way, never silently
# dropped or silently included.
HIGH_PRIVILEGE_PROFILES = frozenset({
    'System Administrator',
})


def _is_high_privilege(name: str) -> bool:
    return name in HIGH_PRIVILEGE_PROFILES


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


def target_object_names(sf):
    """API names of every sobject in the target (DescribeGlobal), or None if it
    can't be read. Used to skip cloned Lookups whose referenceTo object isn't in
    the target (e.g. a managed `hed__Term__c` that Ed Cloud doesn't have) — a
    None result means "couldn't verify", so callers fail *open* (don't drop)."""
    res = None
    try:
        res = sf.describe() or {}
    except Exception:
        try:
            res = sf.restful('sobjects/') or {}
        except Exception:
            return None
    names = {s.get('name') for s in (res.get('sobjects') or []) if s.get('name')}
    return names or None


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
                cloned_fields=None, include_high_privilege: bool = False,
                justification: str = '') -> dict:
    """Full mirror plan for one object.

    Reads the source org's per-parent access, checks each parent name against the
    target's profiles / permission sets, and scopes field grants to fields that
    will exist in the target (cloned_fields ∪ fields already present). Returns:

      {object, source_org, target_org, target_object_exists, scoped,
       matched:[{name, type, object_perms, field_perms, dropped_fields, high_privilege}],
       unmatched:[{name, type}], skipped_locked:[...], high_privilege_excluded:[...],
       counts:{...}}

    cloned_fields: `Object.Field` API names being deployed now (from the clone
    plan). Combined with the target's existing fields to form the allow-list.

    This reads an entire org's cross-profile/permission-set security posture,
    so every call emits an audit event (services.audit) — action
    'ACCESS_MIRROR_PLAN', keyed on source_org->target_org:object, carrying the
    caller-supplied justification. High-privilege profiles (System
    Administrator and equivalents — HIGH_PRIVILEGE_PROFILES) are excluded from
    `matched` by default; pass include_high_privilege=True to include them
    (flagged `high_privilege: true` on their matched entry either way, never
    silently folded in).
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

    matched, unmatched, skipped_locked, high_privilege_excluded = [], [], [], []
    for p in source['parents']:
        present = (p['name'] in catalog['profiles']) if p['type'] == 'Profile' \
            else (p['name'] in catalog['permission_sets'])
        if not present:
            unmatched.append({'name': p['name'], 'type': p['type']})
            continue
        # A license-locked standard/integration profile can't be deployed cleanly,
        # so report it separately instead of emitting an undeployable file.
        if p['type'] == 'Profile' and _is_locked_profile(p['name']):
            skipped_locked.append({'name': p['name'], 'type': p['type']})
            continue
        high_priv = p['type'] == 'Profile' and _is_high_privilege(p['name'])
        if high_priv and not include_high_privilege:
            high_privilege_excluded.append({'name': p['name'], 'type': p['type']})
            continue
        if scoped:
            kept = [fp for fp in p['field_perms'] if fp['field'] in allowed]
            dropped = len(p['field_perms']) - len(kept)
        else:
            kept, dropped = p['field_perms'], 0
        entry = {'name': p['name'], 'type': p['type'],
                 'object_perms': p['object_perms'], 'field_perms': kept,
                 'dropped_fields': dropped, 'high_privilege': high_priv}
        if p['type'] == 'PermissionSet':
            entry['label'] = catalog['permission_sets'].get(p['name'], p['name'])
        matched.append(entry)

    matched_profiles = [m for m in matched if m['type'] == 'Profile']
    matched_permsets = [m for m in matched if m['type'] == 'PermissionSet']
    counts = {
        'source_parents': len(source['parents']),
        'matched': len(matched),
        'matched_profiles': len(matched_profiles),
        'matched_permsets': len(matched_permsets),
        'unmatched': len(unmatched),
        'skipped_locked': len(skipped_locked),
        'high_privilege_excluded': len(high_privilege_excluded),
    }

    audit.emit(
        'ACCESS_MIRROR_PLAN', 'sf_object_permissions',
        f'{source_org}->{target_org}:{object_name}', 'success',
        detail={**counts, 'justification': justification or ''},
    )

    return {
        'object': object_name,
        'source_org': source_org,
        'target_org': target_org,
        'target_object_exists': target_object_exists,
        'scoped': scoped,
        'matched': matched,
        'unmatched': unmatched,
        'skipped_locked': skipped_locked,
        'high_privilege_excluded': high_privilege_excluded,
        'counts': counts,
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
