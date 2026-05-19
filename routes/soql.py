import logging

from flask import Blueprint, jsonify, render_template, request, session

from services import soql_workbench

logger = logging.getLogger(__name__)

soql_bp = Blueprint('soql', __name__, url_prefix='/soql')


# ── Page routes ───────────────────────────────────────────────────────────────

@soql_bp.route('/')
@soql_bp.route('')
def index():
    return render_template('soql/index.html')


# ── API routes ────────────────────────────────────────────────────────────────

@soql_bp.route('/run', methods=['POST'])
def api_run():
    org = session.get('active_org', 'dev')
    user_key = request.remote_addr
    body = request.get_json(silent=True) or {}
    query = body.get('soql', body.get('query', '')).strip()
    all_pages = bool(body.get('all_pages', False))
    if not query:
        return jsonify({'success': False, 'data': None, 'error': 'query is required'}), 400
    try:
        result = soql_workbench.run_query(
            org=org,
            query=query,
            all_pages=all_pages,
            user_key=user_key,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('soql run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/objects', methods=['GET'])
def api_objects():
    org = session.get('active_org', 'dev')
    try:
        objects = soql_workbench.list_objects(org=org)
        return jsonify({'success': True, 'data': objects})
    except Exception as exc:
        logger.exception('soql objects failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/objects/<name>/fields', methods=['GET'])
def api_object_fields(name):
    org = session.get('active_org', 'dev')
    try:
        fields = soql_workbench.list_fields(org=org, object_name=name)
        return jsonify({'success': True, 'data': fields})
    except Exception as exc:
        logger.exception('soql fields failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/saved', methods=['GET'])
def api_saved_get():
    user_key = request.remote_addr
    try:
        queries = soql_workbench.get_saved_queries(user_key=user_key)
        return jsonify({'success': True, 'data': queries})
    except Exception as exc:
        logger.exception('get saved queries failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/saved', methods=['POST'])
def api_saved_post():
    user_key = request.remote_addr
    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    query = body.get('query', '').strip()
    if not name or not query:
        return jsonify({'success': False, 'data': None, 'error': 'name and query are required'}), 400
    try:
        saved = soql_workbench.save_query(user_key=user_key, name=name, query=query)
        return jsonify({'success': True, 'data': saved}), 201
    except Exception as exc:
        logger.exception('save query failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/saved/<int:query_id>', methods=['DELETE'])
def api_saved_delete(query_id):
    user_key = request.remote_addr
    try:
        soql_workbench.delete_saved_query(user_key=user_key, query_id=query_id)
        return jsonify({'success': True, 'data': {'deleted_id': query_id}})
    except Exception as exc:
        logger.exception('delete saved query failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@soql_bp.route('/update', methods=['POST'])
def api_update():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object_name', '').strip()
    record_id = body.get('record_id', '').strip()
    field_name = body.get('field_name', '').strip()
    value = body.get('value')
    if not object_name or not record_id or not field_name:
        return jsonify({'success': False, 'data': None, 'error': 'object_name, record_id and field_name are required'}), 400
    bypass = session.get('bypass_triggers', False)
    try:
        result = soql_workbench.update_record(
            org=org,
            object_name=object_name,
            record_id=record_id,
            field_name=field_name,
            value=value,
            bypass=bypass,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('soql update failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
