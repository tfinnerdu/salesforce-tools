"""Deploy tab — Change Set Builder routes."""
import logging

from flask import Blueprint, render_template, request, session

from services import changeset_builder
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to deploy_api_bp under /api/v1/deploy;
# the old /deploy/<subpath> paths 308-redirect there (register_legacy_json_redirect
# below) so existing MC.api('/deploy/...') calls keep working unmodified.
deploy_bp = Blueprint('deploy', __name__, url_prefix='/deploy')
deploy_api_bp = Blueprint('deploy_api', __name__, url_prefix='/api/v1/deploy')

SUPPORTED_TYPES = ['ApexClass', 'ApexTrigger', 'CustomField', 'Flow', 'PermissionSet', 'ValidationRule']


@deploy_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@deploy_bp.route('/')
@deploy_bp.route('')
def index():
    return render_template('deploy/index.html')


register_legacy_json_redirect(deploy_bp, '/api/v1/deploy')


# ── API routes ────────────────────────────────────────────────────────────────

@deploy_api_bp.route('/components', methods=['GET'])
def api_components():
    component_type = request.args.get('type', '')
    if component_type not in SUPPORTED_TYPES:
        return error_response(
            f'Unsupported type: {component_type!r}. Must be one of {SUPPORTED_TYPES}',
            'INVALID_INPUT', 400)
    org = session.get('active_org', 'dev')
    try:
        components = changeset_builder.list_components(org, component_type)
        return ok(components)
    except Exception as exc:
        logger.exception('list_components failed for type %s', component_type)
        return error_response(str(exc), 'COMPONENTS_FAILED', 500)


@deploy_api_bp.route('/generate', methods=['POST'])
def api_generate():
    body = request.get_json(silent=True) or {}
    components = body.get('components', [])
    if not components:
        return error_response('components is required', 'INVALID_INPUT', 400)
    api_version = body.get('api_version', '65.0')
    try:
        result = changeset_builder.build_package(components, api_version=api_version)
        return ok(result)
    except Exception as exc:
        logger.exception('build_package failed')
        return error_response(str(exc), 'GENERATE_FAILED', 500)
