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


@admin_bp.route('/record-types')
def api_record_types():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_record_types(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('record types failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/email-templates')
def api_email_templates():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_email_templates(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('email templates failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/audit-trail')
def api_audit_trail():
    org = session.get('active_org', 'dev')
    try:
        days = int(request.args.get('days', 7))
    except (ValueError, TypeError):
        days = 7
    try:
        data = admin_service.get_audit_trail(org, days=days)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('audit trail failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/job-queue')
def api_job_queue():
    org = session.get('active_org', 'dev')
    try:
        limit = int(request.args.get('limit', 100))
        data = admin_service.get_apex_job_queue(org, limit=limit)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('job queue failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/login-history')
def api_login_history():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_login_history(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('login history failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/custom-metadata')
def api_custom_metadata_types():
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_metadata_types(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('custom metadata types failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/custom-metadata/<type_name>/records')
def api_custom_metadata_records(type_name):
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_metadata_records(org, type_name)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('custom metadata records failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/custom-settings')
def api_custom_settings():
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_settings(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('custom settings failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/custom-settings/<setting_name>/records')
def api_custom_setting_records(setting_name):
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_setting_records(org, setting_name)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('custom setting records failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/sets')
def api_perm_sets():
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_permission_sets(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm sets failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/users')
def api_perm_users():
    org = session.get('active_org', 'dev')
    search = request.args.get('q', '').strip()
    try:
        from services import perm_auditor
        data = perm_auditor.get_users(org, search=search)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm users failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/user/<user_id>')
def api_perm_user_detail(user_id):
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_user_detail(org, user_id)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm user detail failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/set/<pset_id>')
def api_perm_set_detail(pset_id):
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_pset_detail(org, pset_id)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm set detail failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/object-matrix')
def api_perm_object_matrix():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return jsonify({'success': False, 'error': 'object param required'}), 400
    try:
        from services import perm_auditor
        data = perm_auditor.get_object_access_matrix(org, object_name)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm object matrix failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@admin_bp.route('/permissions/field-matrix')
def api_perm_field_matrix():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return jsonify({'success': False, 'error': 'object param required'}), 400
    try:
        from services import perm_auditor
        data = perm_auditor.get_field_access_matrix(org, object_name)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('perm field matrix failed')
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
