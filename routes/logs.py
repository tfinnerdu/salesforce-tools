import logging

from flask import Blueprint, jsonify, render_template, request, session

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
def api_apex_logs():
    org = session.get('active_org', 'dev')
    since = request.args.get('since')  # ISO datetime string, optional
    try:
        logs = apex_log_reader.list_logs(org=org, since=since)
        return jsonify({'success': True, 'data': logs})
    except Exception as exc:
        logger.exception('apex log list failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/apex/delete-all', methods=['DELETE'])
def api_apex_delete_all():
    org = session.get('active_org', 'dev')
    try:
        result = apex_log_reader.delete_all_logs(org=org)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('delete all logs failed')
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


@logs_bp.route('/apex/cpu-summary')
def api_apex_cpu_summary():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.get_cpu_summary(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('cpu summary failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/stream/subscribe', methods=['POST'])
def api_stream_subscribe():
    """Stub for future Salesforce Streaming API / CometD bridge."""
    # TODO: Implement CometD long-poll bridge
    # Would subscribe to /event/ApexCalloutEventStream or platform events
    return jsonify({
        'success': False,
        'data': None,
        'error': 'Real-time streaming not yet implemented — requires CometD WebSocket bridge.',
    }), 501


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


@logs_bp.route('/trace-flags', methods=['GET'])
def api_trace_flags_list():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.list_trace_flags(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('trace flags list failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/trace-flags/debug-levels', methods=['GET'])
def api_debug_levels():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.list_debug_levels(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('debug levels failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/trace-flags/users', methods=['GET'])
def api_trace_users():
    org = session.get('active_org', 'dev')
    search = request.args.get('q', '')
    try:
        data = apex_log_reader.list_users_for_tracing(org, search=search)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('trace users failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/trace-flags', methods=['POST'])
def api_trace_flags_create():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    entity_id = body.get('entity_id', '').strip()
    entity_type = body.get('entity_type', 'User')
    debug_level_id = body.get('debug_level_id', '').strip()
    duration = int(body.get('duration_minutes', 30))
    if not entity_id or not debug_level_id:
        return jsonify({'success': False, 'data': None, 'error': 'entity_id and debug_level_id required'}), 400
    try:
        data = apex_log_reader.create_trace_flag(org=org, entity_id=entity_id,
                                                  entity_type=entity_type,
                                                  debug_level_id=debug_level_id,
                                                  duration_minutes=duration)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('create trace flag failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/trace-flags/delete-expired', methods=['DELETE'])
def api_trace_flags_delete_expired():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.delete_expired_trace_flags(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('delete expired flags failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@logs_bp.route('/trace-flags/<flag_id>', methods=['DELETE'])
def api_trace_flags_delete(flag_id):
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.delete_trace_flag(org, flag_id)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('delete trace flag failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
