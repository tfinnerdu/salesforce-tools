import logging

from flask import Blueprint, jsonify, render_template, session

from services import apex_log_reader

logger = logging.getLogger(__name__)

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')


# ── Page routes ────────────────────────────────────────────────────────────────

@logs_bp.route('/')
@logs_bp.route('')
def index():
    return render_template('logs/index.html')


# ── API routes ─────────────────────────────────────────────────────────────────

@logs_bp.route('/apex', methods=['GET'])
def api_apex_list():
    org = session.get('active_org', 'dev')
    try:
        logs = apex_log_reader.list_logs(org)
        return jsonify({'success': True, 'data': logs})
    except Exception as exc:
        logger.exception('apex log list failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/apex/<log_id>', methods=['GET'])
def api_apex_detail(log_id):
    org = session.get('active_org', 'dev')
    try:
        body = apex_log_reader.get_log_body(org, log_id)
        parsed = apex_log_reader.parse_log(body)
        return jsonify({'success': True, 'data': parsed})
    except Exception as exc:
        logger.exception('apex log detail failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/apex/<log_id>', methods=['DELETE'])
def api_apex_delete(log_id):
    org = session.get('active_org', 'dev')
    try:
        result = apex_log_reader.delete_log(org, log_id)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('apex log delete failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/flows', methods=['GET'])
def api_flow_errors():
    org = session.get('active_org', 'dev')
    try:
        errors = apex_log_reader.list_flow_errors(org)
        return jsonify({'success': True, 'data': errors})
    except Exception as exc:
        logger.exception('flow errors failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/process-exceptions', methods=['GET'])
def api_process_exceptions():
    org = session.get('active_org', 'dev')
    try:
        exceptions = apex_log_reader.list_process_exceptions(org)
        return jsonify({'success': True, 'data': exceptions})
    except Exception as exc:
        logger.exception('process exceptions failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
