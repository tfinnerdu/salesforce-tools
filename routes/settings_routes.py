import logging

from flask import Blueprint, jsonify, render_template, request, session

from sf_provider import get_sf
from services import collection_manager

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


# ── Page routes ───────────────────────────────────────────────────────────────

@settings_bp.route('/')
@settings_bp.route('')
def index():
    from config import get_org_config, Config
    orgs = ['dev', 'prod', 'sandbox']
    org_configs = {}
    for org in orgs:
        cfg = get_org_config(org)
        org_configs[org] = {'username': cfg.get('username', '')}
    dml_settings = {
        'rate_limit': Config.SF_DML_RATE_LIMIT,
        'bypass_setting': Config.SF_BYPASS_SETTING,
        'bypass_field': Config.SF_BYPASS_FIELD,
    }
    bypass_active = session.get('bypass_triggers', False)
    return render_template('settings/index.html',
                           org_configs=org_configs,
                           dml_settings=dml_settings,
                           bypass_active=bypass_active)


# ── API routes ────────────────────────────────────────────────────────────────

@settings_bp.route('/org/<name>/test', methods=['GET'])
def api_org_test(name):
    try:
        sf = get_sf(name)
        result = sf.query('SELECT Id FROM Account LIMIT 1')
        record_count = result.get('totalSize', 0)
        instance_url = getattr(sf, 'sf_instance', '')
        return jsonify({'success': True, 'org': name, 'record_count': record_count,
                        'instance_url': instance_url})
    except Exception as exc:
        logger.exception('org connection test failed for %s', name)
        return jsonify({'success': False, 'org': name, 'error': str(exc)}), 200


@settings_bp.route('/bypass-triggers', methods=['POST'])
def api_bypass_triggers():
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get('enabled', False))
    session['bypass_triggers'] = enabled
    return jsonify({'success': True, 'data': {'bypass_triggers': enabled}})


@settings_bp.route('/org/switch', methods=['POST'])
def api_org_switch():
    body = request.get_json(silent=True) or {}
    org = body.get('org', '').strip()
    if not org:
        return jsonify({'success': False, 'data': None, 'error': 'org is required'}), 400
    session['active_org'] = org
    return jsonify({'success': True, 'data': {'active_org': org}})


@settings_bp.route('/collections', methods=['GET'])
def api_collections_list():
    try:
        collections = collection_manager.list_collections()
        return jsonify({'success': True, 'data': collections})
    except Exception as exc:
        logger.exception('list collections failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@settings_bp.route('/collections', methods=['POST'])
def api_collections_create():
    if 'file' in request.files:
        uploaded_file = request.files['file']
        try:
            content = uploaded_file.read().decode('utf-8')
            collection = collection_manager.import_collection(content)
            return jsonify({'success': True, 'data': collection}), 201
        except Exception as exc:
            logger.exception('collection import failed')
            return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500

    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    collection_json = body.get('collection_json')
    if not name or not collection_json:
        return jsonify({'success': False, 'data': None, 'error': 'name and collection_json are required'}), 400
    try:
        collection = collection_manager.create_collection(name=name, collection_json=collection_json)
        return jsonify({'success': True, 'data': collection}), 201
    except Exception as exc:
        logger.exception('collection create failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@settings_bp.route('/collections/<int:col_id>/run', methods=['POST'])
def api_collections_run(col_id):
    body = request.get_json(silent=True) or {}
    env_overrides = body.get('env_overrides', {})
    try:
        result = collection_manager.run_collection(col_id=col_id, env_overrides=env_overrides)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('collection run failed for id=%s', col_id)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@settings_bp.route('/collections/<int:col_id>', methods=['DELETE'])
def api_collections_delete(col_id):
    try:
        collection_manager.delete_collection(col_id=col_id)
        return jsonify({'success': True, 'data': {'deleted_id': col_id}})
    except Exception as exc:
        logger.exception('collection delete failed for id=%s', col_id)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
