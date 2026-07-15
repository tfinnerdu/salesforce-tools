import logging

from flask import Blueprint, render_template, request, session

from services import apex_log_reader
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to logs_api_bp under /api/v1/logs;
# the old /logs/<subpath> paths 308-redirect there (register_legacy_json_redirect
# below) so existing MC.api('/logs/...') calls keep working unmodified.
logs_bp = Blueprint('logs', __name__, url_prefix='/logs')
logs_api_bp = Blueprint('logs_api', __name__, url_prefix='/api/v1/logs')


@logs_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ────────────────────────────────────────────────────────────────

@logs_bp.route('/')
@logs_bp.route('')
def index():
    return render_template('logs/index.html')


register_legacy_json_redirect(logs_bp, '/api/v1/logs')


# ── API routes ─────────────────────────────────────────────────────────────────

@logs_api_bp.route('/apex', methods=['GET'])
def api_apex_logs():
    org = session.get('active_org', 'dev')
    since = request.args.get('since')  # ISO datetime string, optional
    try:
        logs = apex_log_reader.list_logs(org=org, since=since)
        return ok(logs)
    except Exception as exc:
        logger.exception('apex log list failed')
        return error_response(str(exc), 'APEX_LOGS_FAILED', 500)


@logs_api_bp.route('/apex/delete-all', methods=['DELETE'])
def api_apex_delete_all():
    org = session.get('active_org', 'dev')
    try:
        result = apex_log_reader.delete_all_logs(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('delete all logs failed')
        return error_response(str(exc), 'APEX_DELETE_ALL_FAILED', 500)


@logs_api_bp.route('/apex/<log_id>', methods=['GET'])
def api_apex_detail(log_id):
    org = session.get('active_org', 'dev')
    try:
        body = apex_log_reader.get_log_body(org, log_id)
        parsed = apex_log_reader.parse_log(body)
        return ok(parsed)
    except Exception as exc:
        logger.exception('apex log detail failed')
        return error_response(str(exc), 'APEX_DETAIL_FAILED', 500)


@logs_api_bp.route('/apex/<log_id>', methods=['DELETE'])
def api_apex_delete(log_id):
    org = session.get('active_org', 'dev')
    try:
        result = apex_log_reader.delete_log(org, log_id)
        return ok(result)
    except Exception as exc:
        logger.exception('apex log delete failed')
        return error_response(str(exc), 'APEX_DELETE_FAILED', 500)


@logs_api_bp.route('/apex/cpu-summary')
def api_apex_cpu_summary():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.get_cpu_summary(org)
        return ok(data)
    except Exception as exc:
        logger.exception('cpu summary failed')
        return error_response(str(exc), 'APEX_CPU_SUMMARY_FAILED', 500)


@logs_api_bp.route('/stream/subscribe', methods=['POST'])
def api_stream_subscribe():
    """Stub for future Salesforce Streaming API / CometD bridge."""
    # TODO: Implement CometD long-poll bridge
    # Would subscribe to /event/ApexCalloutEventStream or platform events
    return error_response(
        'Real-time streaming not yet implemented — requires CometD WebSocket bridge.',
        'NOT_IMPLEMENTED', 501,
    )


@logs_api_bp.route('/flows', methods=['GET'])
def api_flow_errors():
    org = session.get('active_org', 'dev')
    try:
        errors = apex_log_reader.list_flow_errors(org)
        return ok(errors)
    except Exception as exc:
        logger.exception('flow errors failed')
        return error_response(str(exc), 'FLOW_ERRORS_FAILED', 500)


@logs_api_bp.route('/process-exceptions', methods=['GET'])
def api_process_exceptions():
    org = session.get('active_org', 'dev')
    try:
        exceptions = apex_log_reader.list_process_exceptions(org)
        return ok(exceptions)
    except Exception as exc:
        logger.exception('process exceptions failed')
        return error_response(str(exc), 'PROCESS_EXCEPTIONS_FAILED', 500)


@logs_api_bp.route('/trace-flags', methods=['GET'])
def api_trace_flags_list():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.list_trace_flags(org)
        return ok(data)
    except Exception as exc:
        logger.exception('trace flags list failed')
        return error_response(str(exc), 'TRACE_FLAGS_LIST_FAILED', 500)


@logs_api_bp.route('/trace-flags/debug-levels', methods=['GET'])
def api_debug_levels():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.list_debug_levels(org)
        return ok(data)
    except Exception as exc:
        logger.exception('debug levels failed')
        return error_response(str(exc), 'DEBUG_LEVELS_FAILED', 500)


@logs_api_bp.route('/trace-flags/users', methods=['GET'])
def api_trace_users():
    org = session.get('active_org', 'dev')
    search = request.args.get('q', '')
    try:
        data = apex_log_reader.list_users_for_tracing(org, search=search)
        return ok(data)
    except Exception as exc:
        logger.exception('trace users failed')
        return error_response(str(exc), 'TRACE_USERS_FAILED', 500)


@logs_api_bp.route('/trace-flags', methods=['POST'])
def api_trace_flags_create():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    entity_id = body.get('entity_id', '').strip()
    entity_type = body.get('entity_type', 'User')
    debug_level_id = body.get('debug_level_id', '').strip()
    duration = int(body.get('duration_minutes', 30))
    if not entity_id or not debug_level_id:
        return error_response('entity_id and debug_level_id required', 'INVALID_INPUT', 400)
    try:
        data = apex_log_reader.create_trace_flag(org=org, entity_id=entity_id,
                                                  entity_type=entity_type,
                                                  debug_level_id=debug_level_id,
                                                  duration_minutes=duration)
        return ok(data)
    except Exception as exc:
        logger.exception('create trace flag failed')
        return error_response(str(exc), 'TRACE_FLAGS_CREATE_FAILED', 500)


@logs_api_bp.route('/trace-flags/delete-expired', methods=['DELETE'])
def api_trace_flags_delete_expired():
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.delete_expired_trace_flags(org)
        return ok(data)
    except Exception as exc:
        logger.exception('delete expired flags failed')
        return error_response(str(exc), 'TRACE_FLAGS_DELETE_EXPIRED_FAILED', 500)


@logs_api_bp.route('/trace-flags/<flag_id>', methods=['DELETE'])
def api_trace_flags_delete(flag_id):
    org = session.get('active_org', 'dev')
    try:
        data = apex_log_reader.delete_trace_flag(org, flag_id)
        return ok(data)
    except Exception as exc:
        logger.exception('delete trace flag failed')
        return error_response(str(exc), 'TRACE_FLAGS_DELETE_FAILED', 500)
