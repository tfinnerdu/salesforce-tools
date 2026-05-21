import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import crosswalk_diff, schema_diff

logger = logging.getLogger(__name__)

schema_bp = Blueprint('schema', __name__, url_prefix='/schema')


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
    return render_template('schema/org_diff.html')


@schema_bp.route('/metadata-diff')
def metadata_diff_page():
    from services import metadata_diff
    return render_template('schema/metadata_diff.html',
                           metadata_types=metadata_diff.METADATA_TYPES)


@schema_bp.route('/field-usage')
def field_usage():
    return render_template('schema/field_usage.html')


@schema_bp.route('/data-dictionary')
def data_dictionary():
    return render_template('schema/data_dictionary.html')


@schema_bp.route('/apex-search')
def apex_search():
    return render_template('schema/apex_search.html')


@schema_bp.route('/inspect')
def record_inspector():
    return render_template('schema/record_inspector.html')


# ── API routes ────────────────────────────────────────────────────────────────

@schema_bp.route('/crosswalk/upload', methods=['POST'])
def api_crosswalk_upload():
    if 'file' not in request.files:
        return jsonify({'success': False, 'data': None, 'error': 'No file uploaded'}), 400
    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'success': False, 'data': None, 'error': 'Empty filename'}), 400
    try:
        content = uploaded_file.read().decode('utf-8')
        parsed = crosswalk_diff.parse_csv(content)
        return jsonify({'success': True, 'data': parsed})
    except Exception as exc:
        logger.exception('crosswalk upload failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/crosswalk/run', methods=['POST'])
def api_crosswalk_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    mappings = body.get('mappings', [])
    try:
        result = crosswalk_diff.run_live_check(org=org, mappings=mappings)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('crosswalk run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/field-usage/run', methods=['POST'])
def api_field_usage_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    if not sobject:
        return jsonify({'success': False, 'data': None, 'error': 'sobject required'}), 400
    fields = body.get('fields')  # optional list of field names
    try:
        from services import field_usage
        result = field_usage.run(org=org, sobject=sobject, fields=fields)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('field usage run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/data-dictionary/run', methods=['POST'])
def api_data_dictionary_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    if not sobject:
        return jsonify({'success': False, 'data': None, 'error': 'sobject required'}), 400
    try:
        from services import data_dictionary
        result = data_dictionary.get_field_catalog(org=org, sobject=sobject)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('data dictionary failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/apex-search/run', methods=['POST'])
def api_apex_search_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    pattern = body.get('pattern', '').strip()
    if not pattern:
        return jsonify({'success': False, 'data': None, 'error': 'pattern required'}), 400
    if len(pattern) < 2:
        return jsonify({'success': False, 'data': None, 'error': 'pattern must be at least 2 characters'}), 400
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
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('apex search failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/snapshots')
def page_snapshots():
    return render_template('schema/snapshots.html')

@schema_bp.route('/snapshots/list')
def api_snapshots_list():
    from services import schema_snapshot
    org = request.args.get('org', session.get('active_org', 'dev'))
    sobject = request.args.get('sobject', '')
    try:
        data = schema_snapshot.list_snapshots(org=org or None, sobject=sobject or None)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('list snapshots failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500

@schema_bp.route('/snapshots/take', methods=['POST'])
def api_snapshots_take():
    from services import schema_snapshot
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', 'Account').strip()
    label = body.get('label', '').strip() or None
    try:
        data = schema_snapshot.take_snapshot(org=org, sobject=sobject, label=label)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('take snapshot failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500

@schema_bp.route('/snapshots/diff')
def api_snapshots_diff():
    from services import schema_snapshot
    try:
        snap_a = int(request.args.get('a', 0))
        snap_b = int(request.args.get('b', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'data': None, 'error': 'invalid snapshot ids'}), 400
    try:
        data = schema_snapshot.diff_snapshots(snap_a, snap_b)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('diff snapshots failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500

@schema_bp.route('/snapshots/<int:snap_id>', methods=['DELETE'])
def api_snapshots_delete(snap_id):
    from services import schema_snapshot
    try:
        schema_snapshot.delete_snapshot(snap_id)
        return jsonify({'success': True, 'data': None})
    except Exception as exc:
        logger.exception('delete snapshot failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/org-diff/run', methods=['POST'])
def api_org_diff_run():
    left_org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    right_org = body.get('compare_org') or request.args.get('compare_org', 'prod')
    objects = body.get('objects', [])
    try:
        result = schema_diff.run_diff(
            left_org=left_org,
            right_org=right_org,
            objects=objects,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('org diff failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/metadata-diff/run', methods=['POST'])
def api_metadata_diff_run():
    from services import metadata_diff
    left_org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    right_org = body.get('compare_org') or body.get('right_org') or 'prod'
    types = body.get('types', [])
    try:
        result = metadata_diff.run_metadata_diff(left_org, right_org, types)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('metadata diff failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@schema_bp.route('/inspect/run', methods=['POST'])
def api_record_inspect():
    from services import record_inspector
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = (body.get('object') or '').strip()
    record_id = (body.get('record_id') or '').strip()
    external_id_field = (body.get('external_id_field') or '').strip()
    if not object_name or not record_id:
        return jsonify({'success': False, 'data': None,
                        'error': 'object and record_id are required'}), 400
    try:
        result = record_inspector.get_record(org, object_name, record_id,
                                             external_id_field=external_id_field)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('record inspect failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
