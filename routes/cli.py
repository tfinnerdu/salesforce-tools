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
from services import cli_metadata, cli_script
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
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)

    permset = _permset_from(payload)
    permset_name = permset.get('api_name', '')
    flip_fields = [f for f in fields if f.get('mode') == 'flip']
    username = get_org_config(_org()).get('username', '')

    return ok({
        'install': cli_script.install_snippet(),
        'login': cli_script.login_snippet(alias, instance_url),
        'project': cli_script.project_snippet(project, alias, base_path),
        'retrieve': cli_script.retrieve_snippet(alias),
        'backup': cli_script.backup_snippet(flip_fields, alias),
        'verify': cli_script.verify_snippet(flip_fields, alias),
        'deploy_dry_run': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=True),
        'deploy_full': cli_script.deploy_snippet(fields, permset_name, alias, dry_run=False),
        'assign': cli_script.assign_snippet(permset_name, alias, username),
        'members': cli_script._members(fields, permset_name),
        'has_flips': bool(flip_fields),
    })


# ── Package download (zip) ───────────────────────────────────────────────────

@cli_bp.route('/package', methods=['POST'])
def api_package():
    payload = request.get_json(silent=True) or {}
    project = (payload.get('project') or '').strip()
    alias = (payload.get('alias') or '').strip()
    try:
        fields = _validate_fields(payload.get('fields') or [])
        permset = _permset_from(payload)
        zip_bytes, filename = cli_script.build_package_zip(
            project, fields, permset or None, alias)
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
