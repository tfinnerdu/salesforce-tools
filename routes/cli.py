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
from services import cli_clone, cli_fls, cli_layout, cli_metadata, cli_recordtype, cli_script
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

    def _perms(edit):
        perms = cli_fls.human_field_perms(fields, edit)
        seen = {fp['field'] for fp in perms}
        for ef in existing_fields:
            if ef not in seen:
                perms.append({'field': ef, 'readable': True, 'editable': edit})
                seen.add(ef)
        return perms

    permsets = [{'api_name': name, 'label': label, 'description': description,
                 'field_perms': _perms(editable)}]
    if editable and hp.get('readonly_companion'):
        permsets.append({
            'api_name': f'{name}_ReadOnly',
            'label': f'{label} (Read Only)',
            'description': (description + ' Read-only companion.').strip(),
            'field_perms': _perms(False),
        })
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
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)

    permset = _permset_from(payload)
    permset_name = permset.get('api_name', '')
    humans = _human_permsets_from(payload, fields, existing)
    extra_names = [h['api_name'] for h in humans]
    flip_fields = [f for f in fields if f.get('mode') == 'flip']
    username = get_org_config(_org()).get('username', '')
    layout_name = (payload.get('layout_name') or '').strip()
    rt_name = (payload.get('recordtype_name') or '').strip()

    assign_entries = [{'name': permset_name, 'username': username}]
    for h in humans:
        assign_entries.append({'name': h['api_name'], 'username': '<staff-username>'})

    return ok({
        'install': cli_script.install_snippet(),
        'login': cli_script.login_snippet(alias, instance_url),
        'project': cli_script.project_snippet(project, alias, base_path),
        'retrieve': cli_script.retrieve_snippet(alias),
        'backup': cli_script.backup_snippet(flip_fields, alias),
        'verify': cli_script.verify_snippet(flip_fields, alias),
        'deploy_dry_run': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=True,
                                                    extra_permset_names=extra_names),
        'deploy_full': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=False,
                                                 extra_permset_names=extra_names),
        'assign': cli_script.assign_snippets(assign_entries, alias),
        'deploy_dir': cli_script.deploy_dir_snippet(alias, dry_run=False),
        'members': cli_script._members(fields, permset_name, extra_names),
        'has_flips': bool(flip_fields),
        'has_human_permset': bool(humans),
        'layout_retrieve': cli_script.layout_retrieve_snippet(layout_name, alias),
        'layout_deploy': cli_script.layout_deploy_snippet(layout_name, alias, dry_run=False),
        'recordtype_retrieve': cli_script.recordtype_retrieve_snippet(rt_name, alias),
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
        permset = _permset_from(payload)
        humans = _human_permsets_from(payload, fields, existing)
        zip_bytes, filename = cli_script.build_package_zip(
            project, fields, permset or None, alias,
            extra_permsets=humans or None)
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

def _clone_permset(object_name: str, fields: list) -> dict:
    """An access permission set granting read/edit on every cloned field."""
    base = object_name[:-3] if object_name.endswith('__c') else object_name
    name = f'{base}_Access'
    return {
        'api_name': name,
        'label': name.replace('_', ' '),
        'description': f'Field access for cloned {object_name}.',
        'field_perms': cli_fls.human_field_perms(fields, editable=True),
    }


@cli_bp.route('/clone-object/plan', methods=['POST'])
def api_clone_object_plan():
    """Describe the active-org source object → a clone plan (fields + skipped + shell)."""
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    include_shell = bool(payload.get('include_shell'))
    if not obj:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        return ok(cli_clone.plan_from_object(_org(), obj, include_shell=include_shell))
    except Exception as exc:
        logger.exception('cli clone plan failed for %s', obj)
        return error_response(str(exc), 'SF_DESCRIBE_FAILED', 502)


@cli_bp.route('/clone-object/package', methods=['POST'])
def api_clone_object_package():
    """Build the force-app zip for a cloned object (fields + optional shell + permset)."""
    payload = request.get_json(silent=True) or {}
    obj = (payload.get('object') or '').strip()
    project = (payload.get('project') or '').strip()
    alias = (payload.get('alias') or '').strip()
    include_shell = bool(payload.get('include_shell'))
    include_permset = bool(payload.get('include_permset'))
    if not obj:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        plan = cli_clone.plan_from_object(_org(), obj, include_shell=include_shell)
        fields = plan['fields']
        object_shells = [plan['shell']] if plan['shell'] else None
        if not fields and not object_shells:
            return error_response(
                'Nothing to clone — the object has no reproducible custom fields. '
                'Tick "include the object definition" to at least create the object shell.',
                'INVALID_INPUT', 400)
        permset = _clone_permset(obj, fields) if (include_permset and fields) else None
        zip_bytes, filename = cli_script.build_package_zip(
            project or obj, fields, permset, alias, object_shells=object_shells)
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
