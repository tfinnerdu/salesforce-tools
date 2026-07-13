"""CLI tab — Salesforce CLI script + metadata generation (the engine).

Turns a describe-driven field/permission-set plan into the exact artifacts a
sys admin runs locally: `sf` command snippets (PowerShell backtick style) and
a `force-app` metadata package zipped for download. This module is pure and
deterministic — it never touches Salesforce or the filesystem — so every
generated contract is unit- and characterization-testable.

The generated `field-meta.xml` / `permissionset-meta.xml` reproduce the real
Conductor EDA→EDF migration artifacts (see tests/characterization) so a field
authored here deploys identically to one hand-written by the team.

Conventions honored (from the Salesforce CLI field guide):
- PowerShell line continuation is a trailing backtick, never a backslash, and
  never with trailing whitespace after the backtick.
- Sandboxes log in with an explicit `--instance-url`.
- Retrieve is read-only; only deploy mutates. Flips of existing fields carry a
  backup (retrieve to ./_backup) and a verify-first describe.
"""
import io
import zipfile
from xml.sax.saxutils import escape

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
CF_OPEN = '<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">'
PS_OPEN = '<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">'
CO_OPEN = '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">'
PKG_NS = 'http://soap.sforce.com/2006/04/metadata'

# Default Metadata API version for a generated package.xml.
DEFAULT_API_VERSION = '62.0'

# Field types the builder supports, and which attributes each honors. The
# order of tags below mirrors what `sf project retrieve` emits and what the
# Conductor artifacts use, so generated XML matches hand-authored XML.
SUPPORTED_TYPES = (
    'Text', 'TextArea', 'LongTextArea', 'Picklist', 'Checkbox',
    'Number', 'Date', 'DateTime', 'Email', 'Phone', 'Url', 'Lookup',
)
# Types that accept <externalId>/<unique>.
_EXTID_TYPES = {'Text', 'Number', 'Email'}
# Types that accept <required> (Checkbox is always-valued; long text can't be required).
_REQUIRED_TYPES = {'Text', 'TextArea', 'Picklist', 'Number', 'Date', 'DateTime',
                   'Email', 'Phone', 'Url', 'Lookup'}
# Lookup <deleteConstraint> options (Cascade is master-detail only, not offered here).
_DELETE_CONSTRAINTS = {'SetNull', 'Restrict'}


# ── XML: custom field ────────────────────────────────────────────────────────

def _tag(name: str, value) -> str:
    """Single indented element line: <name>value</name> (value XML-escaped)."""
    if isinstance(value, bool):
        value = 'true' if value else 'false'
    return f'    <{name}>{escape(str(value))}</{name}>'


def _value_set_block(picklist: dict) -> str:
    """Render a <valueSet> block from {restricted, sorted, values:[...]}.

    Each value: {value, label, default=False, active=True}. Inactive values
    emit <isActive>false</isActive> (retire, don't delete — existing record
    references survive), matching the guide's picklist discipline.
    """
    restricted = bool(picklist.get('restricted', True))
    sorted_ = bool(picklist.get('sorted', False))
    lines = [
        '    <valueSet>',
        f'        <restricted>{"true" if restricted else "false"}</restricted>',
        '        <valueSetDefinition>',
        f'            <sorted>{"true" if sorted_ else "false"}</sorted>',
    ]
    for v in picklist.get('values', []):
        full = escape(str(v.get('value', '')))
        label = escape(str(v.get('label', v.get('value', ''))))
        default = 'true' if v.get('default') else 'false'
        active_tag = '' if v.get('active', True) else '<isActive>false</isActive>'
        lines.append(
            f'            <value><fullName>{full}</fullName>'
            f'<default>{default}</default>{active_tag}<label>{label}</label></value>'
        )
    lines.append('        </valueSetDefinition>')
    lines.append('    </valueSet>')
    return '\n'.join(lines)


def field_meta_xml(spec: dict) -> str:
    """Render a CustomField `.field-meta.xml` from a field spec.

    Spec keys: api_name, label, type, and type-specific attrs
    (description, required, length, precision, scale, externalId, unique,
    caseSensitive, defaultValue, visibleLines, picklist{...}).

    Element order is fixed per type to match `sf` retrieve output and the
    Conductor artifacts.
    """
    ftype = spec.get('type', 'Text')
    if ftype not in SUPPORTED_TYPES:
        raise ValueError(f'Unsupported field type: {ftype!r}')
    api_name = spec.get('api_name', '')
    if not api_name:
        raise ValueError('field spec requires api_name')

    body = [f'    <fullName>{escape(api_name)}</fullName>']
    if spec.get('description'):
        body.append(_tag('description', spec['description']))
    # externalId comes before label (matches retrieve output / Conductor sample).
    if ftype in _EXTID_TYPES and spec.get('externalId'):
        body.append(_tag('externalId', True))
    body.append(_tag('label', spec.get('label') or api_name))

    if ftype == 'Lookup':
        # A Lookup references its target by object API name (not record Id), so
        # it clones cross-org as long as that object exists in the target.
        ref = (spec.get('referenceTo') or '').strip()
        if not ref:
            raise ValueError('Lookup field spec requires referenceTo (the related object)')
        rel_name = spec.get('relationshipName') or _relationship_name(api_name)
        body.append(_tag('referenceTo', ref))
        body.append(_tag('relationshipLabel', spec.get('relationshipLabel')
                         or spec.get('label') or api_name))
        body.append(_tag('relationshipName', rel_name))

    if ftype in ('Text', 'TextArea', 'LongTextArea'):
        # length: Text default 255, LongTextArea default 32768.
        default_len = 32768 if ftype == 'LongTextArea' else 255
        body.append(_tag('length', int(spec.get('length') or default_len)))
    if ftype == 'Number':
        body.append(_tag('precision', int(spec.get('precision') or 18)))
        body.append(_tag('scale', int(spec.get('scale') or 0)))

    if ftype in _REQUIRED_TYPES:
        body.append(_tag('required', bool(spec.get('required', False))))
    body.append(_tag('trackTrending', False))
    body.append(_tag('type', ftype))

    if ftype == 'Lookup':
        dc = spec.get('deleteConstraint') or 'SetNull'
        body.append(_tag('deleteConstraint', dc if dc in _DELETE_CONSTRAINTS else 'SetNull'))
    if ftype in _EXTID_TYPES and spec.get('unique'):
        body.append(_tag('unique', True))
    # caseSensitive is only valid on a unique Text field.
    if ftype == 'Text' and spec.get('unique'):
        body.append(_tag('caseSensitive', bool(spec.get('caseSensitive', False))))
    if ftype == 'Checkbox':
        body.append(_tag('defaultValue', bool(spec.get('defaultValue', False))))
    if ftype == 'LongTextArea':
        body.append(_tag('visibleLines', int(spec.get('visibleLines') or 3)))
    if ftype == 'Picklist':
        body.append(_value_set_block(spec.get('picklist') or {}))

    return '\n'.join([XML_HEADER, CF_OPEN, *body, '</CustomField>']) + '\n'


def _relationship_name(api_name: str) -> str:
    """Child-relationship API name for a Lookup — the field name minus its __c."""
    base = api_name[:-3] if api_name.endswith('__c') else api_name
    return base or 'Related'


# ── XML: custom object shell ─────────────────────────────────────────────────

def object_meta_xml(shell: dict) -> str:
    """Render a best-effort CustomObject `.object-meta.xml` from a shell spec.

    Spec keys: label, plural_label, name_label, sharing_model. Emits a Text name
    field and a Deployed status — enough to *create* a custom object so its
    fields have somewhere to land. describe doesn't expose sharingModel or an
    auto-number display format, so those are the caller's defaults (see
    cli_clone.object_shell), reviewed before deploying to a new object.
    """
    label = shell.get('label') or shell.get('object') or 'Object'
    plural = shell.get('plural_label') or label
    name_label = shell.get('name_label') or 'Name'
    sharing = shell.get('sharing_model') or 'ReadWrite'
    body = [
        _tag('deploymentStatus', 'Deployed'),
        _tag('label', label),
        '    <nameField>',
        f'        <label>{escape(str(name_label))}</label>',
        '        <type>Text</type>',
        '    </nameField>',
        _tag('pluralLabel', plural),
        _tag('sharingModel', sharing),
    ]
    return '\n'.join([XML_HEADER, CO_OPEN, *body, '</CustomObject>']) + '\n'


# ── XML: permission set ──────────────────────────────────────────────────────

def object_perms_for(objects: list, editable: bool) -> list:
    """Object-permission specs for a set of objects at read or read/write level.

    Read-only grants allowRead; editable also grants create + edit (not delete or
    view/modify-all — those stay a deliberate opt-in). This is what makes a
    metadata-deployed object *visible*, which field FLS alone can't do.
    """
    return [{'object': o, 'read': True, 'create': bool(editable),
             'edit': bool(editable), 'delete': False,
             'view_all': False, 'modify_all': False} for o in objects if o]


def permission_set_xml(api_name: str, label: str, field_perms: list,
                       description: str = '', object_perms: list = None) -> str:
    """Render a PermissionSet `.permissionset-meta.xml`.

    field_perms: [{field: 'Object.Field__c', readable: bool, editable: bool}].
    object_perms: [{object, read, create, edit, delete, view_all, modify_all}] —
    object-level access so the permset opens the object itself, not just its
    fields (field FLS is moot if the object is hidden).
    Emits one single-line entry per permission, matching retrieve output.
    """
    if not api_name:
        raise ValueError('permission set requires api_name')

    def _b(v):
        return 'true' if v else 'false'

    lines = [XML_HEADER, PS_OPEN, _tag('label', label or api_name)]
    if description:
        lines.append(_tag('description', description))
    lines.append(_tag('hasActivationRequired', False))
    for op in (object_perms or []):
        obj = escape(str(op.get('object', '')))
        if not obj:
            continue
        # Sub-elements are all required, in retrieve's alphabetical order.
        lines.append(
            '    <objectPermissions>'
            f'<allowCreate>{_b(op.get("create"))}</allowCreate>'
            f'<allowDelete>{_b(op.get("delete"))}</allowDelete>'
            f'<allowEdit>{_b(op.get("edit"))}</allowEdit>'
            f'<allowRead>{_b(op.get("read", True))}</allowRead>'
            f'<modifyAllRecords>{_b(op.get("modify_all"))}</modifyAllRecords>'
            f'<object>{obj}</object>'
            f'<viewAllRecords>{_b(op.get("view_all"))}</viewAllRecords>'
            '</objectPermissions>'
        )
    for fp in field_perms:
        field = escape(str(fp.get('field', '')))
        readable = 'true' if fp.get('readable', True) else 'false'
        editable = 'true' if fp.get('editable', False) else 'false'
        lines.append(
            f'    <fieldPermissions><field>{field}</field>'
            f'<readable>{readable}</readable><editable>{editable}</editable></fieldPermissions>'
        )
    lines.append('</PermissionSet>')
    return '\n'.join(lines) + '\n'


# ── XML: package manifest ────────────────────────────────────────────────────

def package_xml(fields: list, permset_name: str = '',
                api_version: str = DEFAULT_API_VERSION,
                extra_permset_names: list = None,
                object_names: list = None, layout_names: list = None) -> str:
    """Render a manifest/package.xml listing the package's members.

    object_names adds a CustomObject <types> block (for a cloned object's shell);
    layout_names adds a Layout block (for a pasted layout copied as-is).
    """
    lines = [XML_HEADER, f'<Package xmlns="{PKG_NS}">']
    if object_names:
        lines.append('    <types>')
        for name in object_names:
            lines.append(f'        <members>{escape(name)}</members>')
        lines.append('        <name>CustomObject</name>')
        lines.append('    </types>')
    if fields:
        lines.append('    <types>')
        for f in fields:
            member = escape(f'{f["object"]}.{f["api_name"]}')
            lines.append(f'        <members>{member}</members>')
        lines.append('        <name>CustomField</name>')
        lines.append('    </types>')
    if layout_names:
        lines.append('    <types>')
        for name in layout_names:
            lines.append(f'        <members>{escape(name)}</members>')
        lines.append('        <name>Layout</name>')
        lines.append('    </types>')
    permset_names = ([permset_name] if permset_name else []) + \
        [n for n in (extra_permset_names or []) if n and n != permset_name]
    if permset_names:
        lines.append('    <types>')
        for name in permset_names:
            lines.append(f'        <members>{escape(name)}</members>')
        lines.append('        <name>PermissionSet</name>')
        lines.append('    </types>')
    lines.append(f'    <version>{escape(str(api_version))}</version>')
    lines.append('</Package>')
    return '\n'.join(lines) + '\n'


# ── Command snippets (PowerShell, backtick continuation) ─────────────────────

def install_snippet() -> str:
    """Step 2 — install the CLI and sanity-check the connection (static)."""
    return ('npm install --global @salesforce/cli@latest\n'
            'sf --version\n'
            'sf org list')


def login_snippet(alias: str, instance_url: str) -> str:
    """Step 3 — authorize a sandbox with an explicit instance URL."""
    return (f'sf org login web --instance-url {instance_url} '
            f'--alias {alias or "<alias>"}')


def project_snippet(project: str, alias: str, base_path: str) -> str:
    """Step 4 — generate a project, cd in, and sanity-check metadata access."""
    project = project or '<project>'
    base_path = (base_path or '').rstrip('\\/')
    return (f'sf project generate --name {project}\n'
            f'cd "{base_path}\\{project}"\n'
            f'sf org list metadata --metadata-type Flow --target-org {alias or "<alias>"}')


def retrieve_snippet(alias: str) -> str:
    """Step 5 — pull the metadata types we edit. `CustomObject` carries objects
    and their fields; `PermissionSet` carries FLS. (There is no `Object` type.)"""
    alias = alias or '<alias>'
    return ('sf project retrieve start --target-org ' + alias + ' `\n'
            '  -m CustomObject `\n'
            '  -m PermissionSet')


def _members(fields: list, permset_name: str, extra_permset_names: list = None,
             object_names: list = None, layout_names: list = None) -> list:
    # CustomObject first — a field's object must exist for the same deploy to
    # create its fields (Metadata deploy resolves the dependency within one run).
    members = [f'CustomObject:{name}' for name in (object_names or []) if name]
    members += [f'CustomField:{f["object"]}.{f["api_name"]}' for f in fields]
    # Layouts after fields — a layout references its object's fields.
    members += [f'Layout:{name}' for name in (layout_names or []) if name]
    if permset_name:
        members.append(f'PermissionSet:{permset_name}')
    for name in (extra_permset_names or []):
        if name and name != permset_name:
            members.append(f'PermissionSet:{name}')
    return members


def deploy_snippet(fields: list, permset_name: str, alias: str,
                   dry_run: bool = False, extra_permset_names: list = None,
                   object_names: list = None, layout_names: list = None) -> str:
    """Steps 8/9 — deploy the authored components by name. dry_run adds --dry-run.
    extra_permset_names carries additional permission sets (e.g. the cloned
    human-visibility set) alongside the integration one. object_names carries
    new/cloned CustomObject shells so the object deploys with its fields;
    layout_names carries pasted layouts copied as-is."""
    alias = alias or '<alias>'
    members = _members(fields, permset_name, extra_permset_names, object_names, layout_names)
    lines = ['sf project deploy start `']
    for m in members:
        lines.append(f'  -m "{m}" `')
    tail = f'  -o {alias}'
    if dry_run:
        tail += ' --dry-run'
    lines.append(tail)
    return '\n'.join(lines)


# ── Command composer recipes (explore-from-the-terminal snippets) ────────────

def recipe_soql(object_name: str, fields: list, limit: int = 10) -> str:
    """The SELECT that both the CLI query recipe and the SOQL Workbench link use."""
    obj = object_name or '<Object>'
    cols = ['Id'] + [f for f in (fields or []) if f and f != 'Id']
    return f'SELECT {", ".join(cols)} FROM {obj} LIMIT {int(limit)}'


def recipe_query(object_name: str, fields: list, alias: str, limit: int = 10) -> str:
    return f'sf data query -o {alias or "<alias>"} -q "{recipe_soql(object_name, fields, limit)}"'


def recipe_count(object_name: str, alias: str) -> str:
    return (f'sf data query -o {alias or "<alias>"} '
            f'-q "SELECT COUNT() FROM {object_name or "<Object>"}"')


def recipe_describe(object_name: str, alias: str) -> str:
    return f'sf sobject describe --sobject {object_name or "<Object>"} -o {alias or "<alias>"}'


def recipe_retrieve_object(object_name: str, alias: str) -> str:
    return (f'sf project retrieve start -m "CustomObject:{object_name or "<Object>"}" '
            f'-o {alias or "<alias>"}')


def command_recipes(object_name: str, fields: list, alias: str) -> dict:
    """All composer recipes for one object (+ optional field selection)."""
    return {
        'describe': recipe_describe(object_name, alias),
        'count': recipe_count(object_name, alias),
        'query': recipe_query(object_name, fields, alias),
        'retrieve_object': recipe_retrieve_object(object_name, alias),
        'soql': recipe_soql(object_name, fields),
    }


def deploy_dir_snippet(alias: str, dry_run: bool = False) -> str:
    """Alternative deploy: push the whole force-app folder (no -m). Avoids the
    'No source-backed components present' gotcha when the -m components aren't
    unzipped into the project yet."""
    tail = ' --dry-run' if dry_run else ''
    return f'sf project deploy start --source-dir force-app -o {alias or "<alias>"}{tail}'


def assign_snippet(permset_name: str, alias: str, username: str) -> str:
    """Step 10 — assign the permission set to the integration user."""
    return (f'sf org assign permset --name {permset_name or "<permission-set>"} '
            f'--on-behalf-of {username or "<integration-username>"} '
            f'-o {alias or "<alias>"}')


def assign_snippets(entries: list, alias: str) -> str:
    """One `sf org assign permset` line per (name, username) entry — used when
    more than one permission set is generated (integration + cloned human set,
    which go to different users). entries: [{name, username}]."""
    alias = alias or '<alias>'
    lines = [
        f'sf org assign permset --name {e.get("name") or "<permission-set>"} '
        f'--on-behalf-of {e.get("username") or "<username>"} -o {alias}'
        for e in entries if e.get('name')
    ]
    return '\n'.join(lines)


def layout_list_snippet(alias: str) -> str:
    """List every layout in the source org so you can find a layout's exact
    fullName (``<Object>-<Layout Name>``) to retrieve."""
    return f'sf org list metadata --metadata-type Layout --target-org {alias or "<alias>"}'


def layout_retrieve_snippet(layout_name: str, alias: str) -> str:
    """Retrieve a page layout so it can be pasted into the Layout tool."""
    return (f'sf project retrieve start -m "Layout:{layout_name or "<Object>-<Layout Name>"}" '
            f'-o {alias or "<alias>"}')


def layout_deploy_snippet(layout_name: str, alias: str, dry_run: bool = False) -> str:
    """Deploy the modified page layout."""
    tail = ' --dry-run' if dry_run else ''
    return (f'sf project deploy start -m "Layout:{layout_name or "<Object>-<Layout Name>"}" '
            f'-o {alias or "<alias>"}{tail}')


def recordtype_retrieve_snippet(rt_name: str, alias: str) -> str:
    """Retrieve a record type so it can be pasted into the Record type tool."""
    return (f'sf project retrieve start -m "RecordType:{rt_name or "<Object>.<RecordType>"}" '
            f'-o {alias or "<alias>"}')


def recordtype_deploy_snippet(rt_name: str, alias: str, dry_run: bool = False) -> str:
    """Deploy the modified record type."""
    tail = ' --dry-run' if dry_run else ''
    return (f'sf project deploy start -m "RecordType:{rt_name or "<Object>.<RecordType>"}" '
            f'-o {alias or "<alias>"}{tail}')


def backup_snippet(flip_fields: list, alias: str) -> str:
    """Step 0 (flips only) — retrieve current state of fields being MODIFIED to
    ./_backup so a flip can be diffed or rolled back. Returns '' if no flips."""
    if not flip_fields:
        return ''
    alias = alias or '<alias>'
    lines = ['sf project retrieve start `']
    for f in flip_fields:
        lines.append(f'  -m "CustomField:{f["object"]}.{f["api_name"]}" `')
    lines.append(f'  -o {alias} --target-metadata-dir ./_backup')
    return '\n'.join(lines)


def verify_snippet(flip_fields: list, alias: str) -> str:
    """Step 1 (flips only) — describe the objects and check whether the External
    ID flip is even needed (skip fields already externalId + idLookup, since a
    redeploy overwrites the field's other attributes). Returns '' if no flips."""
    if not flip_fields:
        return ''
    alias = alias or '<alias>'
    objects = sorted({f['object'] for f in flip_fields})
    names = sorted({f['api_name'] for f in flip_fields})
    obj_list = ','.join(f"'{o}'" for o in objects)
    name_list = ','.join(f"'{n}'" for n in names)
    return (
        f'{obj_list} | ForEach-Object {{\n'
        '  "=== $_ ==="\n'
        '  (sf sobject describe --sobject $_ -o ' + alias + ' --json | ConvertFrom-Json).result.fields |\n'
        f'    Where-Object {{ $_.name -in @({name_list}) }} |\n'
        '    Select-Object name, externalId, idLookup, unique, length\n'
        '}'
    )


# ── Package zip ──────────────────────────────────────────────────────────────

def _readme(project: str, fields: list, permset_name: str, alias: str,
            extra_permset_names: list = None, object_names: list = None,
            layout_names: list = None) -> str:
    lines = [
        'SF CLI package — generated by SF Mission Control (CLI tab)',
        '=' * 58,
        '',
        'Unzip and copy the force-app/ tree into your project so the files land at:',
        f'  {base_project_path(project)}\\force-app\\main\\default\\...',
        '',
        'Components:',
    ]
    for name in (object_names or []):
        lines.append(f'  CustomObject  {name}  (best-effort shell — review sharingModel/name field)')
    for f in fields:
        tag = 'flip -> External ID' if f.get('mode') == 'flip' else 'create'
        lines.append(f'  CustomField   {f["object"]}.{f["api_name"]}   ({tag})')
    for name in (layout_names or []):
        lines.append(f'  Layout        {name}  (copied as-is — target must have every field it references)')
    if permset_name:
        lines.append(f'  PermissionSet {permset_name}')
    for name in (extra_permset_names or []):
        lines.append(f'  PermissionSet {name}  (human visibility)')
    lines += ['']
    if object_names or layout_names:
        # A member (-m) deploy can't reliably create an object + its fields in one
        # pass, and a layout needs its fields to exist first; the whole-folder
        # deploy resolves that ordering in a single run.
        lines += [
            'Deploy the whole folder (resolves object/field/layout ordering):',
            '  ' + deploy_dir_snippet(alias, dry_run=True) + '   # validate',
            '  ' + deploy_dir_snippet(alias, dry_run=False) + '   # commit',
        ]
    else:
        lines += [
            'Deploy (validate first):',
            '  ' + deploy_snippet(fields, permset_name, alias, dry_run=True,
                                  extra_permset_names=extra_permset_names).replace('\n', '\n  '),
            '',
            'Then commit:',
            '  ' + deploy_snippet(fields, permset_name, alias, dry_run=False,
                                  extra_permset_names=extra_permset_names).replace('\n', '\n  '),
        ]
    return '\n'.join(lines) + '\n'


def base_project_path(project: str, base_path: str = 'C:\\Doane\\Code\\Salesforce-Projects') -> str:
    base_path = (base_path or '').rstrip('\\/')
    return f'{base_path}\\{project or "<project>"}'


def build_package_zip(project: str, fields: list, permset: dict = None,
                      alias: str = '', api_version: str = DEFAULT_API_VERSION,
                      extra_permsets: list = None, object_shells: list = None,
                      layouts: list = None) -> tuple:
    """Build the force-app metadata package as a zip.

    extra_permsets carries additional permission sets (e.g. the cloned
    human-visibility set) as [{api_name,label,description,field_perms}].
    object_shells carries CustomObject shells (a cloned object's definition) as
    [{object, label, plural_label, name_label, sharing_model}].
    layouts carries pasted page layouts copied as-is as [{full_name, xml}].

    Returns (zip_bytes, filename). Layout:
      force-app/main/default/objects/<Object>/<Object>.object-meta.xml
      force-app/main/default/objects/<Object>/fields/<Field>.field-meta.xml
      force-app/main/default/layouts/<Object>-<Name>.layout-meta.xml
      force-app/main/default/permissionsets/<Name>.permissionset-meta.xml
      manifest/package.xml
      README.txt
    """
    all_permsets = ([permset] if permset and permset.get('field_perms') else []) + \
        [p for p in (extra_permsets or []) if p and p.get('field_perms')]
    object_shells = [s for s in (object_shells or []) if s and s.get('object')]
    layouts = [lay for lay in (layouts or []) if lay and lay.get('full_name') and lay.get('xml')]
    if not fields and not all_permsets and not object_shells and not layouts:
        raise ValueError('Nothing to package — add at least one field, permission set, object, or layout.')

    permset_name = (permset or {}).get('api_name', '') if permset else ''
    extra_names = [p['api_name'] for p in (extra_permsets or []) if p and p.get('field_perms')]
    object_names = [s['object'] for s in object_shells]
    layout_names = [lay['full_name'] for lay in layouts]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for s in object_shells:
            path = (f'force-app/main/default/objects/{s["object"]}/'
                    f'{s["object"]}.object-meta.xml')
            zf.writestr(path, object_meta_xml(s))
        for f in fields:
            path = (f'force-app/main/default/objects/{f["object"]}/fields/'
                    f'{f["api_name"]}.field-meta.xml')
            zf.writestr(path, field_meta_xml(f))
        for lay in layouts:
            path = f'force-app/main/default/layouts/{lay["full_name"]}.layout-meta.xml'
            zf.writestr(path, lay['xml'])
        for ps in all_permsets:
            name = ps['api_name']
            path = f'force-app/main/default/permissionsets/{name}.permissionset-meta.xml'
            zf.writestr(path, permission_set_xml(
                name, ps.get('label', name),
                ps.get('field_perms', []), ps.get('description', ''),
                ps.get('object_perms')))
        zf.writestr('manifest/package.xml',
                    package_xml(fields, permset_name, api_version, extra_names,
                                object_names, layout_names))
        zf.writestr('README.txt',
                    _readme(project, fields, permset_name, alias, extra_names,
                            object_names, layout_names))

    safe = ''.join(c for c in (project or 'package') if c.isalnum() or c in '-_') or 'package'
    return buf.getvalue(), f'sf-cli-package-{safe}.zip'
