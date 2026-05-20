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


@schema_bp.route('/field-usage')
def field_usage():
    return render_template('schema/field_usage.html')


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
