"""CLI blueprint — guided Salesforce CLI script + metadata generator.

Page route renders the vertical builder; data/action routes live under the
same `/cli` prefix (this app's convention — the blueprint prefix is the
namespace). Read-only against Salesforce: it describes objects/fields to drive
the pickers and prefill External-ID flips, but never deploys — the generated
`sf` commands run on the sys admin's own machine.

Responses use the shared error envelope (utils.responses) — a superset of the
app's {success,data} envelope, so MC.api is unaffected. `g.request_id` is set
per request for the envelope's request_id.
"""
import logging

from flask import Blueprint, Response, render_template, request, session

from config import Config, get_org_config
from services import (cli_access_mirror, cli_clone, cli_fls, cli_layout,
                      cli_metadata, cli_recordtype, cli_script)
from sf_provider import available_orgs
from utils.responses import error_response, new_request_id, ok

logger = logging.getLogger(__name__)

cli_bp = Blueprint('cli', __name__, url_prefix='/cli')


@cli_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


def _org() -> str:
    return session.get('active_org', Config.DEFAULT_ORG)


# ── Page ─────────────────────────────────────────────────────────────────────

@cli_bp.route('/')
@cli_bp.route('')
def index():
    return render_template(
        'cli/index.html',
        available_orgs=available_orgs(),
        active_org=_org(),
        default_instance_url=Config.CLI_DEFAULT_INSTANCE_URL,
        default_base_path=Config.CLI_PROJECT_BASE_PATH,
        default_alias=Config.CLI_DEFAULT_ALIAS,
        default_project=Config.CLI_DEFAULT_PROJECT,
        default_permset=Config.CLI_DEFAULT_PERMSET,
        default_permset_label=Config.CLI_DEFAULT_PERMSET.replace('_', ' '),
        supported_types=list(cli_script.SUPPORTED_TYPES),
    )


# ── Describe-driven metadata (read-only) ─────────────────────────────────────

@cli_bp.route('/objects')
def api_objects():
    try:
        return ok(cli_metadata.list_objects(_org()))
    except Exception as exc:
        logger.exception('cli objects list failed')
        return error_response(str(exc), 'SF_DESCRIBE_FAILED', 502)


@cli_bp.route('/objects/<object_name>/fields')
def api_fields(object_name):
    try:
        return ok(cli_metadata.describe_fields(_org(), object_name))
    except Exception as exc:
        logger.exception('cli field describe failed for %s', object_name)
        return error_response(str(exc), 'SF_DESCRIBE_FAILED', 502)


# ── Plan validation (shared by generate + package) ───────────────────────────

def _validate_fields(fields) -> list:
    """Validate + normalize the field list. Raises ValueError on bad input."""
    if not isinstance(fields, list):
        raise ValueError('fields must be a list')
    clean = []
    for i, f in enumerate(fields):
        obj = (f.get('object') or '').strip()
        api = (f.get('api_name') or '').strip()
        ftype = (f.get('type') or '').strip()
        where = f'field #{i + 1}'
        if not obj:
            raise ValueError(f'{where}: object is required')
        if not api:
            raise ValueError(f'{where}: field API name is required')
        if not api.endswith('__c'):
            raise ValueError(f'{where}: custom field API name must end with "__c" (got "{api}")')
        if ftype not in cli_script.SUPPORTED_TYPES:
            raise ValueError(f'{where}: unsupported type "{ftype}"')
        if ftype == 'Picklist' and not (f.get('picklist') or {}).get('values'):
            raise ValueError(f'{where}: a Picklist needs at least one value')
        if ftype == 'Lookup' and not (f.get('referenceTo') or '').strip():
            raise ValueError(f'{where}: a Lookup needs a related object (referenceTo)')
        clean.append(f)
    return clean


def _permset_from(payload) -> dict:
    """Return a normalized permset dict or {} if none was defined."""
    ps = payload.get('permset') or {}
    name = (ps.get('api_name') or '').strip()
    if not name:
        return {}
    return {
        'api_name': name,
        'label': (ps.get('label') or name).strip(),
        'description': (ps.get('description') or '').strip(),
        'field_perms': ps.get('field_perms') or [],
    }


def _object_shells_from(payload) -> list:
    """Normalize the new-object definitions (create fresh CustomObjects) from the
    builder. Each entry: {object, label, plural_label, name_label, sharing_model}.
    Raises ValueError on a malformed API name."""
    out = []
    for item in (payload.get('new_objects') or []):
        obj = (item.get('object') or '').strip()
        if not obj:
            continue
        if not obj.endswith('__c'):
            raise ValueError(f'new object API name must end with "__c" (got "{obj}")')
        label = (item.get('label') or obj[:-3].replace('_', ' ')).strip()
        out.append({
            'object': obj,
            'label': label,
            'plural_label': (item.get('plural_label') or f'{label}s').strip(),
            'name_label': (item.get('name_label') or 'Name').strip(),
            'sharing_model': (item.get('sharing_model') or 'ReadWrite').strip(),
        })
    return out


def _tab_settings_for(objects) -> list:
    """Permission-set tab-visibility entries that make a custom object's tab show
    in the App Launcher / nav for assignees (Visible = on by default)."""
    return [{'tab': o, 'visibility': 'Visible'} for o in objects if o]


def _tabs_from_objects(objects) -> list:
    """CustomTab specs for custom objects (only `__c` objects get a generated
    tab — standard objects already have one)."""
    return [{'object': o} for o in objects if o and o.endswith('__c')]


def _layouts_from(payload) -> list:
    """Normalize pasted page layouts to copy as-is: [{full_name, xml}]. Each needs
    a full name (<Object>-<Layout Name>) and Layout XML. Raises ValueError on a
    malformed entry."""
    out = []
    for item in (payload.get('layouts') or []):
        full = (item.get('full_name') or '').strip()
        xml = item.get('xml') or ''
        if not full and not xml.strip():
            continue
        if not full:
            raise ValueError('a pasted layout needs its full name (e.g. RoomAssignment__c-Room Assignment Layout)')
        if '<Layout' not in xml:
            raise ValueError(f'the pasted content for "{full}" is not a Layout (.layout-meta.xml)')
        out.append({'full_name': full, 'xml': xml})
    return out


def _existing_fields_from(payload) -> list:
    """Validate + normalize the existing-field list (fields that already exist in
    the org and just need visibility). Each entry is an `Object.Field` API name.
    Raises ValueError on a malformed entry."""
    out = []
    for item in (payload.get('existing_fields') or []):
        name = (item or '').strip()
        if not name:
            continue
        obj, _, fld = name.partition('.')
        if not obj or not fld:
            raise ValueError(f'existing field "{name}" must be in Object.Field form (e.g. Case.Group_Information__c)')
        out.append(name)
    return out


def _human_permsets_from(payload, fields, existing_fields=None) -> list:
    """Build the cloned human-visibility permission set(s) from the plan.

    plan.human_permset = {api_name, label, description, editable, readonly_companion}.
    Field permissions cover the built fields AND any existing fields (fields that
    already exist and only need visibility). Returns [] if no name; one permset
    at the chosen access level; and, when `editable` + `readonly_companion`, a
    second read-only "<name>_ReadOnly" set for a view-only audience.
    """
    hp = payload.get('human_permset') or {}
    name = (hp.get('api_name') or '').strip()
    existing_fields = existing_fields or []
    if not name or (not fields and not existing_fields):
        return []
    label = (hp.get('label') or name).strip()
    description = (hp.get('description') or '').strip()
    editable = bool(hp.get('editable'))

    grant_object = bool(hp.get('object_access'))

    def _perms(edit):
        perms = cli_fls.human_field_perms(fields, edit)
        seen = {fp['field'] for fp in perms}
        for ef in existing_fields:
            if ef not in seen:
                perms.append({'field': ef, 'readable': True, 'editable': edit})
                seen.add(ef)
        return perms

    def _objects_of(field_perms):
        objs = []
        for fp in field_perms:
            obj = (fp.get('field') or '').split('.', 1)[0]
            if obj and obj not in objs:
                objs.append(obj)
        return objs

    def _make(name_, label_, desc_, edit_):
        fp = _perms(edit_)
        ps = {'api_name': name_, 'label': label_, 'description': desc_, 'field_perms': fp}
        if grant_object:   # open the object itself, not just its fields
            ps['object_perms'] = cli_script.object_perms_for(_objects_of(fp), edit_)
        return ps

    permsets = [_make(name, label, description, editable)]
    if editable and hp.get('readonly_companion'):
        permsets.append(_make(f'{name}_ReadOnly', f'{label} (Read Only)',
                              (description + ' Read-only companion.').strip(), False))
    return permsets


# ── Field-Level Security clone (read a reference field's visibility) ──────────

@cli_bp.route('/fls')
def api_fls():
    src = (request.args.get('org') or _org()).strip()
    obj = (request.args.get('object') or '').strip()
    field = (request.args.get('field') or '').strip()
    if not obj or not field:
        return error_response('object and field are required', 'INVALID_INPUT', 400)
    if src not in Config.AVAILABLE_ORGS:
        return error_response(f'Unknown org: {src}', 'INVALID_INPUT', 400)
    try:
        return ok(cli_fls.read_field_fls(src, obj, field))
    except Exception as exc:
        logger.exception('cli fls read failed for %s.%s in %s', obj, field, src)
        return error_response(str(exc), 'SF_FLS_READ_FAILED', 502)


# ── Record type: picklist availability (paste + inject a picklistValues block) ─

@cli_bp.route('/recordtype/picklists', methods=['POST'])
def api_recordtype_picklists():
    rt_xml = (request.get_json(silent=True) or {}).get('rt_xml') or ''
    if '<RecordType' not in rt_xml:
        return error_response('Paste a retrieved RecordType (.recordType-meta.xml) first.', 'INVALID_INPUT', 400)
    return ok({'picklists': cli_recordtype.list_picklists(rt_xml)})


@cli_bp.route('/recordtype', methods=['POST'])
def api_recordtype():
    payload = request.get_json(silent=True) or {}
    rt_xml = payload.get('rt_xml') or ''
    if '<RecordType' not in rt_xml:
        return error_response('Paste a retrieved RecordType (.recordType-meta.xml) first.', 'INVALID_INPUT', 400)
    try:
        result = cli_recordtype.add_picklist_values(
            rt_xml,
            (payload.get('field') or '').strip(),
            payload.get('values') or [],
            default=(payload.get('default') or '').strip() or None,
        )
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    return ok(result)


# ── Command composer: describe-driven sf command recipes ─────────────────────

@cli_bp.route('/recipes', methods=['POST'])
def api_recipes():
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    fields = [f for f in (payload.get('fields') or []) if f]
    alias = (payload.get('alias') or '').strip()
    return ok(cli_script.command_recipes(obj, fields, alias))


# ── Page layout: add fields to a pasted layout (org-to-org clone-assist) ─────

@cli_bp.route('/layout/sections', methods=['POST'])
def api_layout_sections():
    layout_xml = (request.get_json(silent=True) or {}).get('layout_xml') or ''
    if '<Layout' not in layout_xml:
        return error_response('Paste a retrieved Layout (.layout-meta.xml) first.', 'INVALID_INPUT', 400)
    return ok({'sections': cli_layout.list_sections(layout_xml)})


@cli_bp.route('/layout', methods=['POST'])
def api_layout():
    payload = request.get_json(silent=True) or {}
    layout_xml = payload.get('layout_xml') or ''
    if '<Layout' not in layout_xml:
        return error_response('Paste a retrieved Layout (.layout-meta.xml) first.', 'INVALID_INPUT', 400)
    try:
        result = cli_layout.place_fields(
            layout_xml,
            payload.get('fields') or [],
            (payload.get('behavior') or 'Edit').strip(),
            section=(payload.get('section') or '').strip() or None,
            new_section=(payload.get('new_section') or '').strip() or None,
        )
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    return ok(result)


# ── Snippet generation ───────────────────────────────────────────────────────

@cli_bp.route('/generate', methods=['POST'])
def api_generate():
    payload = request.get_json(silent=True) or {}
    alias = (payload.get('alias') or '').strip()
    instance_url = (payload.get('instance_url') or Config.CLI_DEFAULT_INSTANCE_URL).strip()
    project = (payload.get('project') or '').strip()
    base_path = (payload.get('base_path') or Config.CLI_PROJECT_BASE_PATH).strip()
    try:
        fields = _validate_fields(payload.get('fields') or [])
        existing = _existing_fields_from(payload)
        object_shells = _object_shells_from(payload)
        layouts = _layouts_from(payload)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)

    permset = _permset_from(payload)
    permset_name = permset.get('api_name', '')
    humans = _human_permsets_from(payload, fields, existing)
    object_names = [s['object'] for s in object_shells]
    # A freshly-built object has no tab (invisible in the App Launcher) — offer to
    # generate one + grant its visibility in the human permset.
    tab_objects = object_names if payload.get('generate_tabs') else []
    tab_member_names = [t['object'] for t in _tabs_from_objects(tab_objects)]
    if tab_member_names and humans:
        tab_settings = _tab_settings_for(tab_member_names)
        for h in humans:
            h['tab_settings'] = tab_settings
    extra_names = [h['api_name'] for h in humans]
    layout_member_names = [lay['full_name'] for lay in layouts]
    flip_fields = [f for f in fields if f.get('mode') == 'flip']
    username = get_org_config(_org()).get('username', '')
    layout_name = (payload.get('layout_name') or '').strip()
    rt_name = (payload.get('recordtype_name') or '').strip()
    # Retrieve from a source org (e.g. EDA), deploy to the target Alias. Blank
    # retrieve-alias falls back to the target alias (single-org case).
    layout_retrieve_alias = (payload.get('layout_retrieve_alias') or '').strip() or alias
    rt_retrieve_alias = (payload.get('rt_retrieve_alias') or '').strip() or alias

    assign_entries = [{'name': permset_name, 'username': username}]
    for h in humans:
        # Default the visibility permset to the same integration username (a real,
        # runnable value) — the admin edits it if it should go to staff instead.
        assign_entries.append({'name': h['api_name'], 'username': username or '<staff-username>'})

    return ok({
        'install': cli_script.install_snippet(),
        'login': cli_script.login_snippet(alias, instance_url),
        'project': cli_script.project_snippet(project, alias, base_path),
        'retrieve': cli_script.retrieve_snippet(alias),
        'backup': cli_script.backup_snippet(flip_fields, alias),
        'verify': cli_script.verify_snippet(flip_fields, alias),
        'deploy_dry_run': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=True,
                                                    extra_permset_names=extra_names,
                                                    object_names=object_names,
                                                    layout_names=layout_member_names,
                                                    tab_names=tab_member_names),
        'deploy_full': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=False,
                                                 extra_permset_names=extra_names,
                                                 object_names=object_names,
                                                 layout_names=layout_member_names,
                                                 tab_names=tab_member_names),
        'assign': cli_script.assign_snippets(assign_entries, alias),
        'deploy_dir': cli_script.deploy_dir_snippet(alias, dry_run=False),
        'members': cli_script._members(fields, permset_name, extra_names, object_names,
                                       layout_member_names, tab_names=tab_member_names),
        'has_flips': bool(flip_fields),
        'has_human_permset': bool(humans),
        'has_new_objects': bool(object_names),
        'has_tabs': bool(tab_member_names),
        'has_layouts': bool(layout_member_names),
        'layout_list': cli_script.layout_list_snippet(layout_retrieve_alias),
        'layout_retrieve': cli_script.layout_retrieve_snippet(layout_name, layout_retrieve_alias),
        'layout_deploy': cli_script.layout_deploy_snippet(layout_name, alias, dry_run=False),
        'recordtype_retrieve': cli_script.recordtype_retrieve_snippet(rt_name, rt_retrieve_alias),
        'recordtype_deploy': cli_script.recordtype_deploy_snippet(rt_name, alias, dry_run=False),
    })


# ── Package download (zip) ───────────────────────────────────────────────────

@cli_bp.route('/package', methods=['POST'])
def api_package():
    payload = request.get_json(silent=True) or {}
    project = (payload.get('project') or '').strip()
    alias = (payload.get('alias') or '').strip()
    try:
        fields = _validate_fields(payload.get('fields') or [])
        existing = _existing_fields_from(payload)
        object_shells = _object_shells_from(payload)
        layouts = _layouts_from(payload)
        permset = _permset_from(payload)
        humans = _human_permsets_from(payload, fields, existing)
        object_names = [s['object'] for s in object_shells]
        tab_objects = object_names if payload.get('generate_tabs') else []
        tabs = _tabs_from_objects(tab_objects)
        if tabs and humans:
            tab_settings = _tab_settings_for([t['object'] for t in tabs])
            for h in humans:
                h['tab_settings'] = tab_settings
        zip_bytes, filename = cli_script.build_package_zip(
            project, fields, permset or None, alias,
            extra_permsets=humans or None, object_shells=object_shells or None,
            layouts=layouts or None, tabs=tabs or None)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    except Exception as exc:
        logger.exception('cli package build failed')
        return error_response(str(exc), 'PACKAGE_FAILED', 500)

    return Response(
        zip_bytes,
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ── Clone a whole object's schema into a package ─────────────────────────────

def _clone_permset(object_name: str, fields: list, include_tab: bool = False) -> dict:
    """An access permission set granting read/edit on every cloned field.

    When include_tab is set, it also grants visibility on the object's generated
    Custom Tab, so an assignee sees the object in the App Launcher / nav.
    """
    base = object_name[:-3] if object_name.endswith('__c') else object_name
    name = f'{base}_Access'
    ps = {
        'api_name': name,
        'label': name.replace('_', ' '),
        'description': f'Object + field access for cloned {object_name}.',
        'field_perms': cli_fls.human_field_perms(fields, editable=True),
        # A cloned object is hidden by default — grant object access so it's usable.
        'object_perms': cli_script.object_perms_for([object_name], editable=True),
    }
    if include_tab and object_name.endswith('__c'):
        ps['tab_settings'] = _tab_settings_for([object_name])
    return ps


def _source_org(payload) -> str:
    """The org whose schema the clone reads from (defaults to the active org)."""
    src = (payload.get('source_org') or _org()).strip()
    if src not in Config.AVAILABLE_ORGS:
        raise ValueError(f'Unknown source org: {src}')
    return src


def _target_org(payload) -> str:
    """The org the clone deploys to — whose profile/permission-set names the
    access mirror matches against (defaults to the active org)."""
    tgt = (payload.get('target_org') or _org()).strip()
    if tgt not in Config.AVAILABLE_ORGS:
        raise ValueError(f'Unknown target org: {tgt}')
    return tgt


def _require_justification(payload) -> str:
    """A short reason is required before reading/mirroring another org's
    security posture (mirror_access) — a real, server-side-enforced control,
    not just a client-side modal. Raises ValueError if missing or too short."""
    just = (payload.get('justification') or '').strip()
    if len(just) < 10:
        raise ValueError(
            'A short justification (at least 10 characters) is required before '
            'reading or mirroring another org\'s security posture.')
    return just


def _target_object_names(target_org: str):
    """The target org's sObject API-name set, for the Lookup-resolution check, or
    None if it can't be read — callers then fail *open* (don't drop lookups)."""
    try:
        return cli_access_mirror.target_object_names(cli_access_mirror.get_sf(target_org))
    except Exception:
        logger.exception('cli target object-name fetch failed for %s', target_org)
        return None


# ── Access mirror: reproduce a source org's access by name in the target ──────

@cli_bp.route('/access-mirror/plan', methods=['POST'])
def api_access_mirror_plan():
    """Preview which source-org profiles / permission sets grant access to an
    object, and which of those names exist in the target (matched vs unmatched).

    Reads another org's full security posture, so a short justification is
    required (server-enforced, not just a UI modal) and every call is audited."""
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    if not obj:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        source = _source_org(payload)
        target = _target_org(payload)
        justification = _require_justification(payload)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    cloned_fields = [f for f in (payload.get('cloned_fields') or []) if f]
    include_high_privilege = bool(payload.get('include_high_privilege'))
    try:
        return ok(cli_access_mirror.mirror_plan(
            source, target, obj, cloned_fields,
            include_high_privilege=include_high_privilege, justification=justification))
    except Exception as exc:
        logger.exception('cli access-mirror plan failed for %s', obj)
        return error_response(str(exc), 'SF_ACCESS_READ_FAILED', 502)


@cli_bp.route('/clone-object/plan', methods=['POST'])
def api_clone_object_plan():
    """Describe a source-org object → a clone plan (fields + skipped + shell)."""
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    include_shell = bool(payload.get('include_shell'))
    mirror_access = bool(payload.get('mirror_access'))
    include_high_privilege = bool(payload.get('include_high_privilege'))
    if not obj:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        source = _source_org(payload)
        target = _target_org(payload) if mirror_access else None
        justification = _require_justification(payload) if mirror_access else ''
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    # With a known target, skip cloning Lookups whose referenceTo object isn't there.
    target_objects = _target_object_names(target) if target else None
    try:
        plan = cli_clone.plan_from_object(source, obj, include_shell=include_shell,
                                          target_objects=target_objects)
    except Exception as exc:
        logger.exception('cli clone plan failed for %s', obj)
        return error_response(str(exc), 'SF_DESCRIBE_FAILED', 502)

    # Preview the name-matched access mirror alongside the field plan when asked,
    # scoped to the fields this clone will actually deploy.
    if mirror_access:
        try:
            cloned_fields = [f'{obj}.{f["api_name"]}' for f in plan['fields']]
            plan['mirror'] = cli_access_mirror.mirror_plan(
                source, target, obj, cloned_fields,
                include_high_privilege=include_high_privilege, justification=justification)
        except Exception:
            logger.exception('cli access-mirror preview failed for %s', obj)
            plan['mirror_error'] = 'Could not read access from the source/target org.'
    return ok(plan)


@cli_bp.route('/clone-object/package', methods=['POST'])
def api_clone_object_package():
    """Build the force-app zip for a cloned object.

    Beyond the fields (+ optional shell + access permset), Phase 2 can ride in a
    Custom Tab (`include_tab`, so the object shows in the App Launcher) and a
    name-matched access mirror (`mirror_access`, reproducing the source org's
    profile + permission-set grants for the object onto same-named metadata in
    the target)."""
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    project = (payload.get('project') or '').strip()
    alias = (payload.get('alias') or '').strip()
    include_shell = bool(payload.get('include_shell'))
    include_permset = bool(payload.get('include_permset'))
    include_tab = bool(payload.get('include_tab'))
    mirror_access = bool(payload.get('mirror_access'))
    include_high_privilege = bool(payload.get('include_high_privilege'))
    if not obj:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        source = _source_org(payload)
        target = _target_org(payload) if mirror_access else None
        justification = _require_justification(payload) if mirror_access else ''
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    # With a known target, skip cloning Lookups whose referenceTo object isn't there.
    target_objects = _target_object_names(target) if target else None
    try:
        plan = cli_clone.plan_from_object(source, obj, include_shell=include_shell,
                                          target_objects=target_objects)
        fields = plan['fields']
        object_shells = [plan['shell']] if plan['shell'] else None
        tabs = _tabs_from_objects([obj]) if include_tab else None

        profiles = extra_permsets = None
        if mirror_access:
            cloned_fields = [f'{obj}.{f["api_name"]}' for f in fields]
            mplan = cli_access_mirror.mirror_plan(
                source, target, obj, cloned_fields,
                include_high_privilege=include_high_privilege, justification=justification)
            mprofiles, mpermsets = cli_access_mirror.split_grants(mplan['matched'])
            profiles = mprofiles or None
            extra_permsets = mpermsets or None

        if not fields and not object_shells and not tabs and not profiles \
                and not extra_permsets:
            return error_response(
                'Nothing to clone — the object has no reproducible custom fields. '
                'Tick "include the object definition" to at least create the object shell.',
                'INVALID_INPUT', 400)
        permset = _clone_permset(obj, fields, include_tab) if (include_permset and fields) else None
        zip_bytes, filename = cli_script.build_package_zip(
            project or obj, fields, permset, alias, object_shells=object_shells,
            tabs=tabs, extra_permsets=extra_permsets, profiles=profiles)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    except Exception as exc:
        logger.exception('cli clone package failed for %s', obj)
        return error_response(str(exc), 'PACKAGE_FAILED', 500)

    return Response(
        zip_bytes,
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
