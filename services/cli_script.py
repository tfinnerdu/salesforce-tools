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
PKG_NS = 'http://soap.sforce.com/2006/04/metadata'

# Default Metadata API version for a generated package.xml.
DEFAULT_API_VERSION = '62.0'

# Field types the builder supports, and which attributes each honors. The
# order of tags below mirrors what `sf project retrieve` emits and what the
# Conductor artifacts use, so generated XML matches hand-authored XML.
SUPPORTED_TYPES = (
    'Text', 'TextArea', 'LongTextArea', 'Picklist', 'Checkbox',
    'Number', 'Date', 'DateTime', 'Email', 'Phone', 'Url',
)
# Types that accept <externalId>/<unique>.
_EXTID_TYPES = {'Text', 'Number', 'Email'}
# Types that accept <required> (Checkbox is always-valued; long text can't be required).
_REQUIRED_TYPES = {'Text', 'TextArea', 'Picklist', 'Number', 'Date', 'DateTime', 'Email', 'Phone', 'Url'}


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


# ── XML: permission set ──────────────────────────────────────────────────────

def permission_set_xml(api_name: str, label: str, field_perms: list,
                       description: str = '') -> str:
    """Render a PermissionSet `.permissionset-meta.xml`.

    field_perms: [{field: 'Object.Field__c', readable: bool, editable: bool}].
    Emits one single-line <fieldPermissions> per entry, in the given order
    (matches the Conductor integration permission set).
    """
    if not api_name:
        raise ValueError('permission set requires api_name')
    lines = [XML_HEADER, PS_OPEN, _tag('label', label or api_name)]
    if description:
        lines.append(_tag('description', description))
    lines.append(_tag('hasActivationRequired', False))
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
                extra_permset_names: list = None) -> str:
    """Render a manifest/package.xml listing CustomField + PermissionSet members."""
    lines = [XML_HEADER, f'<Package xmlns="{PKG_NS}">']
    if fields:
        lines.append('    <types>')
        for f in fields:
            member = escape(f'{f["object"]}.{f["api_name"]}')
            lines.append(f'        <members>{member}</members>')
        lines.append('        <name>CustomField</name>')
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


def _members(fields: list, permset_name: str, extra_permset_names: list = None) -> list:
    members = [f'CustomField:{f["object"]}.{f["api_name"]}' for f in fields]
    if permset_name:
        members.append(f'PermissionSet:{permset_name}')
    for name in (extra_permset_names or []):
        if name and name != permset_name:
            members.append(f'PermissionSet:{name}')
    return members


def deploy_snippet(fields: list, permset_name: str, alias: str,
                   dry_run: bool = False, extra_permset_names: list = None) -> str:
    """Steps 8/9 — deploy the authored components by name. dry_run adds --dry-run.
    extra_permset_names carries additional permission sets (e.g. the cloned
    human-visibility set) alongside the integration one."""
    alias = alias or '<alias>'
    members = _members(fields, permset_name, extra_permset_names)
    lines = ['sf project deploy start `']
    for m in members:
        lines.append(f'  -m "{m}" `')
    tail = f'  -o {alias}'
    if dry_run:
        tail += ' --dry-run'
    lines.append(tail)
    return '\n'.join(lines)


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


def layout_retrieve_snippet(layout_name: str, alias: str) -> str:
    """Retrieve a page layout so it can be pasted into the Layout tool."""
    return (f'sf project retrieve start -m "Layout:{layout_name or "<Object>-<Layout Name>"}" '
            f'-o {alias or "<alias>"}')


def layout_deploy_snippet(layout_name: str, alias: str, dry_run: bool = False) -> str:
    """Deploy the modified page layout."""
    tail = ' --dry-run' if dry_run else ''
    return (f'sf project deploy start -m "Layout:{layout_name or "<Object>-<Layout Name>"}" '
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
            extra_permset_names: list = None) -> str:
    lines = [
        'SF CLI package — generated by SF Mission Control (CLI tab)',
        '=' * 58,
        '',
        'Unzip and copy the force-app/ tree into your project so the files land at:',
        f'  {base_project_path(project)}\\force-app\\main\\default\\...',
        '',
        'Components:',
    ]
    for f in fields:
        tag = 'flip -> External ID' if f.get('mode') == 'flip' else 'create'
        lines.append(f'  CustomField   {f["object"]}.{f["api_name"]}   ({tag})')
    if permset_name:
        lines.append(f'  PermissionSet {permset_name}')
    for name in (extra_permset_names or []):
        lines.append(f'  PermissionSet {name}  (human visibility)')
    lines += [
        '',
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
                      extra_permsets: list = None) -> tuple:
    """Build the force-app metadata package as a zip.

    extra_permsets carries additional permission sets (e.g. the cloned
    human-visibility set) as [{api_name,label,description,field_perms}].

    Returns (zip_bytes, filename). Layout:
      force-app/main/default/objects/<Object>/fields/<Field>.field-meta.xml
      force-app/main/default/permissionsets/<Name>.permissionset-meta.xml
      manifest/package.xml
      README.txt
    """
    all_permsets = ([permset] if permset and permset.get('field_perms') else []) + \
        [p for p in (extra_permsets or []) if p and p.get('field_perms')]
    if not fields and not all_permsets:
        raise ValueError('Nothing to package — add at least one field or a permission set.')

    permset_name = (permset or {}).get('api_name', '') if permset else ''
    extra_names = [p['api_name'] for p in (extra_permsets or []) if p and p.get('field_perms')]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in fields:
            path = (f'force-app/main/default/objects/{f["object"]}/fields/'
                    f'{f["api_name"]}.field-meta.xml')
            zf.writestr(path, field_meta_xml(f))
        for ps in all_permsets:
            name = ps['api_name']
            path = f'force-app/main/default/permissionsets/{name}.permissionset-meta.xml'
            zf.writestr(path, permission_set_xml(
                name, ps.get('label', name),
                ps.get('field_perms', []), ps.get('description', '')))
        zf.writestr('manifest/package.xml',
                    package_xml(fields, permset_name, api_version, extra_names))
        zf.writestr('README.txt',
                    _readme(project, fields, permset_name, alias, extra_names))

    safe = ''.join(c for c in (project or 'package') if c.isalnum() or c in '-_') or 'package'
    return buf.getvalue(), f'sf-cli-package-{safe}.zip'
