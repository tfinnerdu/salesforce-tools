import logging

from flask import Blueprint, jsonify, render_template, request, session

from services import admin_service

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ── Page routes ───────────────────────────────────────────────────────────────

@admin_bp.route('/')
@admin_bp.route('')
def index():
    return render_template('admin/index.html')


# ── API routes ────────────────────────────────────────────────────────────────

@admin_bp.route('/scheduled-jobs')
def api_scheduled_jobs():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_scheduled_jobs(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('scheduled jobs failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/test-coverage')
def api_test_coverage():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_test_coverage(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('test coverage failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/deploy-history')
def api_deploy_history():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_deploy_history(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('deploy history failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/users')
def api_users():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_user_audit(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('user audit failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/integrations')
def api_integrations():
    org = session.get('active_org', 'dev')
    try:
        from services import integration_inventory
        data = integration_inventory.get_all(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('integrations failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/platform-events')
def api_platform_events():
    org = session.get('active_org', 'dev')
    try:
        from services import platform_events
        data = platform_events.get_all(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('platform events failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/anonymizer/objects', methods=['GET'])
def api_anonymizer_objects():
    try:
        from services import anonymizer
        return jsonify({'success': True, 'data': anonymizer.list_objects()})
    except Exception as exc:
        logger.exception('anonymizer list_objects failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/anonymizer/preview', methods=['POST'])
def api_anonymizer_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    field_names = body.get('fields', [])
    if not object_name:
        return jsonify({'success': False, 'data': None, 'error': 'object is required'}), 400
    try:
        from services import anonymizer
        result = anonymizer.preview(org=org, object_name=object_name, field_names=field_names)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('anonymizer preview failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/anonymizer/run', methods=['POST'])
def api_anonymizer_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    field_names = body.get('fields', [])
    dry_run = bool(body.get('dry_run', True))
    if not object_name or not field_names:
        return jsonify({'success': False, 'data': None, 'error': 'object and fields are required'}), 400
    try:
        from services import anonymizer
        result = anonymizer.run(org=org, object_name=object_name, field_names=field_names, dry_run=dry_run)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('anonymizer run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
