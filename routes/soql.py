import logging

from flask import Blueprint, render_template, request, session

from services import soql_workbench
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to soql_api_bp under /api/v1/soql;
# the old /soql/<subpath> paths 308-redirect there (register_legacy_json_redirect
# below) so existing MC.api('/soql/...') calls keep working unmodified.
soql_bp = Blueprint('soql', __name__, url_prefix='/soql')
soql_api_bp = Blueprint('soql_api', __name__, url_prefix='/api/v1/soql')


@soql_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@soql_bp.route('/')
@soql_bp.route('')
def index():
    return render_template('soql/index.html')


register_legacy_json_redirect(soql_bp, '/api/v1/soql')


# ── API routes ────────────────────────────────────────────────────────────────

@soql_api_bp.route('/run', methods=['POST'])
def api_run():
    org = session.get('active_org', 'dev')
    user_key = request.remote_addr
    body = request.get_json(silent=True) or {}
    query = body.get('soql', body.get('query', '')).strip()
    all_pages = bool(body.get('all_pages', False))
    if not query:
        return error_response('query is required', 'INVALID_INPUT', 400)
    try:
        result = soql_workbench.run_query(
            org=org,
            query=query,
            all_pages=all_pages,
            user_key=user_key,
        )
        return ok(result)
    except Exception as exc:
        logger.exception('soql run failed')
        return error_response(str(exc), 'RUN_FAILED', 500)


@soql_api_bp.route('/objects', methods=['GET'])
def api_objects():
    org = session.get('active_org', 'dev')
    try:
        objects = soql_workbench.list_objects(org=org)
        return ok(objects)
    except Exception as exc:
        logger.exception('soql objects failed')
        return error_response(str(exc), 'OBJECTS_FAILED', 500)


@soql_api_bp.route('/objects/<name>/fields', methods=['GET'])
def api_object_fields(name):
    org = session.get('active_org', 'dev')
    try:
        fields = soql_workbench.list_fields(org=org, object_name=name)
        return ok(fields)
    except Exception as exc:
        logger.exception('soql fields failed')
        return error_response(str(exc), 'OBJECT_FIELDS_FAILED', 500)


@soql_api_bp.route('/saved', methods=['GET'])
def api_saved_get():
    user_key = request.remote_addr
    try:
        queries = soql_workbench.get_saved_queries(user_key=user_key)
        return ok(queries)
    except Exception as exc:
        logger.exception('get saved queries failed')
        return error_response(str(exc), 'SAVED_GET_FAILED', 500)


@soql_api_bp.route('/saved', methods=['POST'])
def api_saved_post():
    user_key = request.remote_addr
    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    query = body.get('soql', body.get('query', '')).strip()
    if not name or not query:
        return error_response('name and query are required', 'INVALID_INPUT', 400)
    try:
        saved = soql_workbench.save_query(user_key=user_key, name=name, query=query)
        return ok(saved, 201)
    except Exception as exc:
        logger.exception('save query failed')
        return error_response(str(exc), 'SAVED_POST_FAILED', 500)


@soql_api_bp.route('/saved/<int:query_id>', methods=['DELETE'])
def api_saved_delete(query_id):
    user_key = request.remote_addr
    try:
        soql_workbench.delete_saved_query(user_key=user_key, query_id=query_id)
        return ok({'deleted_id': query_id})
    except Exception as exc:
        logger.exception('delete saved query failed')
        return error_response(str(exc), 'SAVED_DELETE_FAILED', 500)


@soql_api_bp.route('/history', methods=['GET'])
def api_query_history():
    org = session.get('active_org', 'dev')
    user_key = session.get('user_key', 'default')
    try:
        data = soql_workbench.get_query_history(user_key=user_key, org=org)
        return ok(data)
    except Exception as exc:
        logger.exception('query history failed')
        return error_response(str(exc), 'QUERY_HISTORY_FAILED', 500)

@soql_api_bp.route('/history/<int:history_id>', methods=['DELETE'])
def api_delete_history(history_id):
    from db import get_cursor, db_available
    if not db_available():
        return ok({'deleted': False})
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM query_history WHERE id = %s", (history_id,))
        return ok({'deleted': True})
    except Exception as exc:
        logger.exception('delete history failed')
        return error_response(str(exc), 'DELETE_HISTORY_FAILED', 500)


@soql_api_bp.route('/update', methods=['POST'])
def api_update():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object_name', '').strip()
    record_id = body.get('record_id', '').strip()
    field_name = body.get('field_name', '').strip()
    value = body.get('value')
    if not object_name or not record_id or not field_name:
        return error_response('object_name, record_id and field_name are required', 'INVALID_INPUT', 400)
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
        return ok(result)
    except Exception as exc:
        logger.exception('soql update failed')
        return error_response(str(exc), 'UPDATE_FAILED', 500)
