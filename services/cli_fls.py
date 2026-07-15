"""CLI tab — Field-Level Security (visibility) cloning.

Reads a reference field's read/edit-by-parent (profile / permission set) map
from a source org (e.g. EDA) via the standard FieldPermissions object, so a new
Ed Cloud field can be given human visibility that mirrors what EDA had. Modeled
on perm_auditor.get_field_access_matrix (same query shape + sf.query_all path).

Read-only against Salesforce. The synthesis helpers are pure. The clone reads
FLS from a *source* org that may differ from the active working org.
"""
import logging

from services import audit
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _soql_escape(value: str) -> str:
    """Escape a value for embedding inside a single-quoted SOQL literal."""
    return (value or '').replace('\\', '\\\\').replace("'", "\\'")


def read_field_fls(org: str, sobject: str, field: str) -> dict:
    """Return the visibility (FLS) map for one field in `org`."""
    result = read_field_fls_from(get_sf(org), sobject, field)
    # This reads which profiles/permission sets can see a field across the
    # whole org -- a genuine security-posture export, not a benign describe.
    audit.emit('FLS_READ', 'sf_field_permissions', f'{org}:{sobject}.{field}', 'success',
               detail={'parent_count': result['summary']['total']})
    return result


def read_field_fls_from(sf, sobject: str, field: str) -> dict:
    """FLS map from an injected SF client (see read_field_fls).

    Returns {object, field, parents:[{name,type,read,edit}], summary:{...}}.
    A parent is a Profile (name via Parent.Profile.Name) or a PermissionSet
    (name via Parent.Label). `summary.suggested_editable` is True when any
    parent had edit — a sensible default access level for the cloned permset.
    """
    sobject = (sobject or '').strip()
    field = (field or '').strip()
    field_api = field if '.' in field else f'{sobject}.{field}'
    soql = (
        "SELECT Field, Parent.Label, Parent.Profile.Name, Parent.IsOwnedByProfile, "
        "PermissionsRead, PermissionsEdit "
        "FROM FieldPermissions "
        f"WHERE SobjectType = '{_soql_escape(sobject)}' "
        f"AND Field = '{_soql_escape(field_api)}' "
        "ORDER BY Parent.Profile.Name NULLS LAST, Parent.Label"
    )
    res = sf.query_all(soql)

    parents = []
    for r in res.get('records', []):
        parent = r.get('Parent') or {}
        is_profile = bool(parent.get('IsOwnedByProfile'))
        prof_name = (parent.get('Profile') or {}).get('Name') if is_profile else None
        parents.append({
            'name': prof_name or parent.get('Label') or 'Unknown',
            'type': 'Profile' if is_profile else 'PermissionSet',
            'read': bool(r.get('PermissionsRead')),
            'edit': bool(r.get('PermissionsEdit')),
        })

    read_parents = [p['name'] for p in parents if p['read']]
    edit_parents = [p['name'] for p in parents if p['edit']]
    profiles = sorted({p['name'] for p in parents if p['type'] == 'Profile' and p['read']})
    return {
        'object': sobject,
        'field': field_api,
        'parents': parents,
        'summary': {
            'total': len(parents),
            'read_count': len(read_parents),
            'edit_count': len(edit_parents),
            'any_read': bool(read_parents),
            'any_edit': bool(edit_parents),
            'suggested_editable': bool(edit_parents),
            # Profiles that can read it in the source org — who to assign the
            # cloned permission set to (assignment is per-user, by profile).
            'read_profiles': profiles,
        },
    }


def human_field_perms(fields: list, editable: bool) -> list:
    """Build permission-set fieldPermissions for the built fields at one access
    level (read always; edit per `editable`). Used to synthesize the cloned
    human-visibility permission set from the CLI builder's field list."""
    perms = []
    for f in fields:
        obj = (f.get('object') or '').strip()
        api = (f.get('api_name') or '').strip()
        if obj and api:
            perms.append({'field': f'{obj}.{api}', 'readable': True, 'editable': bool(editable)})
    return perms
