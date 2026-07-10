"""Deploy tab — Change Set Builder routes."""
import logging

from flask import Blueprint, jsonify, render_template, request, session

from services import changeset_builder

logger = logging.getLogger(__name__)

deploy_bp = Blueprint('deploy', __name__, url_prefix='/deploy')

SUPPORTED_TYPES = ['ApexClass', 'ApexTrigger', 'CustomField', 'Flow', 'PermissionSet', 'ValidationRule']


# ── Page routes ───────────────────────────────────────────────────────────────

@deploy_bp.route('/')
@deploy_bp.route('')
def index():
    return render_template('deploy/index.html')


# ── API routes ────────────────────────────────────────────────────────────────

@deploy_bp.route('/components', methods=['GET'])
def api_components():
    component_type = request.args.get('type', '')
    if component_type not in SUPPORTED_TYPES:
        return jsonify({
            'success': False,
            'data': None,
            'error': f'Unsupported type: {component_type!r}. Must be one of {SUPPORTED_TYPES}',
        }), 400
    org = session.get('active_org', 'dev')
    try:
        components = changeset_builder.list_components(org, component_type)
        return jsonify({'success': True, 'data': components})
    except Exception as exc:
        logger.exception('list_components failed for type %s', component_type)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@deploy_bp.route('/generate', methods=['POST'])
def api_generate():
    body = request.get_json(silent=True) or {}
    components = body.get('components', [])
    if not components:
        return jsonify({'success': False, 'data': None, 'error': 'components is required'}), 400
    api_version = body.get('api_version', '65.0')
    try:
        result = changeset_builder.build_package(components, api_version=api_version)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('build_package failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500

    # TODO: Auto-deploy (not yet wired)
    # sf.restful('metadata/deployments', method='POST', ...) with package zip
