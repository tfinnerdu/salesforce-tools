import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from services import crosswalk_diff, schema_diff
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to schema_api_bp under
# /api/v1/schema; the old /schema/<subpath> paths 308-redirect there
# (register_legacy_json_redirect below) so existing MC.api('/schema/...')
# calls keep working unmodified.
schema_bp = Blueprint('schema', __name__, url_prefix='/schema')
schema_api_bp = Blueprint('schema_api', __name__, url_prefix='/api/v1/schema')


@schema_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@schema_bp.route('/')
@schema_bp.route('')
def index():
    return redirect(url_for('schema.crosswalk'))


@schema_bp.route('/crosswalk')
def crosswalk():
    return render_template('schema/crosswalk_diff.html')


@schema_bp.route('/org-diff')
def org_diff():
    from sf_provider import available_orgs
    return render_template('schema/org_diff.html',
                           available_orgs=available_orgs(),
                           active_org=session.get('active_org', 'dev'))


@schema_bp.route('/metadata-diff')
def metadata_diff_page():
    from services import metadata_diff
    from sf_provider import available_orgs
    return render_template('schema/metadata_diff.html',
                           metadata_types=metadata_diff.METADATA_TYPES,
                           available_orgs=available_orgs(),
                           active_org=session.get('active_org', 'dev'))


@schema_bp.route('/field-usage')
def field_usage():
    return render_template('schema/field_usage.html')


@schema_bp.route('/field-finder')
def field_finder():
    return render_template('schema/field_finder.html')


@schema_bp.route('/data-dictionary')
def data_dictionary():
    return render_template('schema/data_dictionary.html')


@schema_bp.route('/apex-search')
def apex_search():
    return render_template('schema/apex_search.html')


@schema_bp.route('/inspect')
def record_inspector():
    return render_template('schema/record_inspector.html')


@schema_bp.route('/snapshots')
def page_snapshots():
    return render_template('schema/snapshots.html')


register_legacy_json_redirect(schema_bp, '/api/v1/schema')


# ── API routes ────────────────────────────────────────────────────────────────

@schema_api_bp.route('/crosswalk/upload', methods=['POST'])
def api_crosswalk_upload():
    if 'file' not in request.files:
        return error_response('No file uploaded', 'INVALID_INPUT', 400)
    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return error_response('Empty filename', 'EMPTY_FILENAME', 400)
    try:
        content = uploaded_file.read().decode('utf-8')
        parsed = crosswalk_diff.parse_csv(content)
        return ok(parsed)
    except Exception as exc:
        logger.exception('crosswalk upload failed')
        return error_response(str(exc), 'CROSSWALK_UPLOAD_FAILED', 500)


@schema_api_bp.route('/crosswalk/run', methods=['POST'])
def api_crosswalk_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    mappings = body.get('mappings', [])
    try:
        result = crosswalk_diff.run_live_check(org=org, mappings=mappings)
        return ok(result)
    except Exception as exc:
        logger.exception('crosswalk run failed')
        return error_response(str(exc), 'CROSSWALK_RUN_FAILED', 500)


@schema_api_bp.route('/field-usage/run', methods=['POST'])
def api_field_usage_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    if not sobject:
        return error_response('sobject required', 'INVALID_INPUT', 400)
    fields = body.get('fields')  # optional list of field names
    try:
        from services import field_usage
        result = field_usage.run(org=org, sobject=sobject, fields=fields)
        return ok(result)
    except Exception as exc:
        logger.exception('field usage run failed')
        return error_response(str(exc), 'FIELD_USAGE_RUN_FAILED', 500)


@schema_api_bp.route('/field-finder/run', methods=['POST'])
def api_field_finder_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    field = body.get('field', '').strip()
    if not field:
        return error_response('field required', 'INVALID_INPUT', 400)
    include_standard = bool(body.get('include_standard', False))
    try:
        from services import field_locator
        result = field_locator.find(org=org, field_name=field,
                                    include_standard=include_standard)
        return ok(result)
    except Exception as exc:
        logger.exception('field finder failed')
        return error_response(str(exc), 'FIELD_FINDER_RUN_FAILED', 500)


@schema_api_bp.route('/data-dictionary/run', methods=['POST'])
def api_data_dictionary_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    if not sobject:
        return error_response('sobject required', 'INVALID_INPUT', 400)
    try:
        from services import data_dictionary
        result = data_dictionary.get_field_catalog(org=org, sobject=sobject)
        return ok(result)
    except Exception as exc:
        logger.exception('data dictionary failed')
        return error_response(str(exc), 'DATA_DICTIONARY_RUN_FAILED', 500)


@schema_api_bp.route('/apex-search/run', methods=['POST'])
def api_apex_search_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    pattern = body.get('pattern', '').strip()
    if not pattern:
        return error_response('pattern required', 'INVALID_INPUT', 400)
    if len(pattern) < 2:
        return error_response('pattern must be at least 2 characters', 'PATTERN_TOO_SHORT', 400)
    case_sensitive = bool(body.get('case_sensitive', False))
    include_classes = bool(body.get('include_classes', True))
    include_triggers = bool(body.get('include_triggers', True))
    try:
        from services import apex_code_search
        result = apex_code_search.search(
            org=org,
            pattern=pattern,
            case_sensitive=case_sensitive,
            include_classes=include_classes,
            include_triggers=include_triggers,
        )
        return ok(result)
    except Exception as exc:
        logger.exception('apex search failed')
        return error_response(str(exc), 'APEX_SEARCH_RUN_FAILED', 500)


@schema_api_bp.route('/snapshots/list')
def api_snapshots_list():
    from services import schema_snapshot
    org = request.args.get('org', session.get('active_org', 'dev'))
    sobject = request.args.get('sobject', '')
    try:
        data = schema_snapshot.list_snapshots(org=org or None, sobject=sobject or None)
        return ok(data)
    except Exception as exc:
        logger.exception('list snapshots failed')
        return error_response(str(exc), 'SNAPSHOTS_LIST_FAILED', 500)


@schema_api_bp.route('/snapshots/take', methods=['POST'])
def api_snapshots_take():
    from services import schema_snapshot
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', 'Account').strip()
    label = body.get('label', '').strip() or None
    try:
        data = schema_snapshot.take_snapshot(org=org, sobject=sobject, label=label)
        return ok(data)
    except Exception as exc:
        logger.exception('take snapshot failed')
        return error_response(str(exc), 'SNAPSHOTS_TAKE_FAILED', 500)


@schema_api_bp.route('/snapshots/diff')
def api_snapshots_diff():
    from services import schema_snapshot
    try:
        snap_a = int(request.args.get('a', 0))
        snap_b = int(request.args.get('b', 0))
    except (ValueError, TypeError):
        return error_response('invalid snapshot ids', 'INVALID_INPUT', 400)
    try:
        data = schema_snapshot.diff_snapshots(snap_a, snap_b)
        return ok(data)
    except Exception as exc:
        logger.exception('diff snapshots failed')
        return error_response(str(exc), 'SNAPSHOTS_DIFF_FAILED', 500)


@schema_api_bp.route('/snapshots/<int:snap_id>', methods=['DELETE'])
def api_snapshots_delete(snap_id):
    from services import schema_snapshot
    try:
        schema_snapshot.delete_snapshot(snap_id)
        return ok(None)
    except Exception as exc:
        logger.exception('delete snapshot failed')
        return error_response(str(exc), 'SNAPSHOTS_DELETE_FAILED', 500)


@schema_api_bp.route('/org-diff/run', methods=['POST'])
def api_org_diff_run():
    left_org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    right_org = body.get('compare_org') or body.get('right_org') or 'prod'
    objects = body.get('objects', [])
    try:
        result = schema_diff.run_diff(
            left_org=left_org,
            right_org=right_org,
            objects=objects,
        )
        return ok(result)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    except Exception as exc:
        logger.exception('org diff failed')
        return error_response(str(exc), 'ORG_DIFF_RUN_FAILED', 500)


@schema_api_bp.route('/metadata-diff/run', methods=['POST'])
def api_metadata_diff_run():
    from services import metadata_diff
    left_org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    right_org = body.get('compare_org') or body.get('right_org') or 'prod'
    types = body.get('types', [])
    try:
        result = metadata_diff.run_metadata_diff(left_org, right_org, types)
        return ok(result)
    except ValueError as exc:
        return error_response(str(exc), 'INVALID_INPUT', 400)
    except Exception as exc:
        logger.exception('metadata diff failed')
        return error_response(str(exc), 'METADATA_DIFF_RUN_FAILED', 500)


@schema_api_bp.route('/inspect/run', methods=['POST'])
def api_record_inspect():
    from services import record_inspector
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = (body.get('object') or '').strip()
    record_id = (body.get('record_id') or '').strip()
    external_id_field = (body.get('external_id_field') or '').strip()
    if not object_name or not record_id:
        return error_response('object and record_id are required', 'INVALID_INPUT', 400)
    try:
        result = record_inspector.get_record(org, object_name, record_id,
                                             external_id_field=external_id_field)
        return ok(result)
    except Exception as exc:
        logger.exception('record inspect failed')
        return error_response(str(exc), 'RECORD_INSPECT_FAILED', 500)
