import logging

from flask import Blueprint, render_template, request, session

from services import admin_service
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to admin_api_bp under
# /api/v1/admin; the old /admin/<subpath> paths 308-redirect there
# (register_legacy_json_redirect below) so existing MC.api('/admin/...')
# calls keep working unmodified.
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
admin_api_bp = Blueprint('admin_api', __name__, url_prefix='/api/v1/admin')


@admin_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@admin_bp.route('/')
@admin_bp.route('')
def index():
    return render_template('admin/index.html')


register_legacy_json_redirect(admin_bp, '/api/v1/admin')


# ── API routes ────────────────────────────────────────────────────────────────

@admin_api_bp.route('/scheduled-jobs')
def api_scheduled_jobs():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_scheduled_jobs(org)
        return ok(data)
    except Exception as exc:
        logger.exception('scheduled jobs failed')
        return error_response(str(exc), 'SCHEDULED_JOBS_FAILED', 500)


@admin_api_bp.route('/test-coverage')
def api_test_coverage():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_test_coverage(org)
        return ok(data)
    except Exception as exc:
        logger.exception('test coverage failed')
        return error_response(str(exc), 'TEST_COVERAGE_FAILED', 500)


@admin_api_bp.route('/deploy-history')
def api_deploy_history():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_deploy_history(org)
        return ok(data)
    except Exception as exc:
        logger.exception('deploy history failed')
        return error_response(str(exc), 'DEPLOY_HISTORY_FAILED', 500)


@admin_api_bp.route('/users')
def api_users():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_user_audit(org)
        return ok(data)
    except Exception as exc:
        logger.exception('user audit failed')
        return error_response(str(exc), 'USERS_FAILED', 500)


@admin_api_bp.route('/integrations')
def api_integrations():
    org = session.get('active_org', 'dev')
    try:
        from services import integration_inventory
        data = integration_inventory.get_all(org)
        return ok(data)
    except Exception as exc:
        logger.exception('integrations failed')
        return error_response(str(exc), 'INTEGRATIONS_FAILED', 500)


@admin_api_bp.route('/platform-events')
def api_platform_events():
    org = session.get('active_org', 'dev')
    try:
        from services import platform_events
        data = platform_events.get_all(org)
        return ok(data)
    except Exception as exc:
        logger.exception('platform events failed')
        return error_response(str(exc), 'PLATFORM_EVENTS_FAILED', 500)


@admin_api_bp.route('/record-types')
def api_record_types():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_record_types(org)
        return ok(data)
    except Exception as exc:
        logger.exception('record types failed')
        return error_response(str(exc), 'RECORD_TYPES_FAILED', 500)


@admin_api_bp.route('/email-templates')
def api_email_templates():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_email_templates(org)
        return ok(data)
    except Exception as exc:
        logger.exception('email templates failed')
        return error_response(str(exc), 'EMAIL_TEMPLATES_FAILED', 500)


@admin_api_bp.route('/audit-trail')
def api_audit_trail():
    org = session.get('active_org', 'dev')
    try:
        days = int(request.args.get('days', 7))
    except (ValueError, TypeError):
        days = 7
    try:
        data = admin_service.get_audit_trail(org, days=days)
        return ok(data)
    except Exception as exc:
        logger.exception('audit trail failed')
        return error_response(str(exc), 'AUDIT_TRAIL_FAILED', 500)


@admin_api_bp.route('/job-queue')
def api_job_queue():
    org = session.get('active_org', 'dev')
    try:
        limit = int(request.args.get('limit', 100))
        data = admin_service.get_apex_job_queue(org, limit=limit)
        return ok(data)
    except Exception as exc:
        logger.exception('job queue failed')
        return error_response(str(exc), 'JOB_QUEUE_FAILED', 500)


@admin_api_bp.route('/login-history')
def api_login_history():
    org = session.get('active_org', 'dev')
    try:
        data = admin_service.get_login_history(org)
        return ok(data)
    except Exception as exc:
        logger.exception('login history failed')
        return error_response(str(exc), 'LOGIN_HISTORY_FAILED', 500)


@admin_api_bp.route('/custom-metadata')
def api_custom_metadata_types():
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_metadata_types(org)
        return ok(data)
    except Exception as exc:
        logger.exception('custom metadata types failed')
        return error_response(str(exc), 'CUSTOM_METADATA_TYPES_FAILED', 500)


@admin_api_bp.route('/custom-metadata/<type_name>/records')
def api_custom_metadata_records(type_name):
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_metadata_records(org, type_name)
        return ok(data)
    except Exception as exc:
        logger.exception('custom metadata records failed')
        return error_response(str(exc), 'CUSTOM_METADATA_RECORDS_FAILED', 500)


@admin_api_bp.route('/custom-settings')
def api_custom_settings():
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_settings(org)
        return ok(data)
    except Exception as exc:
        logger.exception('custom settings failed')
        return error_response(str(exc), 'CUSTOM_SETTINGS_FAILED', 500)


@admin_api_bp.route('/custom-settings/<setting_name>/records')
def api_custom_setting_records(setting_name):
    org = session.get('active_org', 'dev')
    try:
        from services import custom_config_viewer
        data = custom_config_viewer.get_custom_setting_records(org, setting_name)
        return ok(data)
    except Exception as exc:
        logger.exception('custom setting records failed')
        return error_response(str(exc), 'CUSTOM_SETTING_RECORDS_FAILED', 500)


@admin_api_bp.route('/permissions/sets')
def api_perm_sets():
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_permission_sets(org)
        return ok(data)
    except Exception as exc:
        logger.exception('perm sets failed')
        return error_response(str(exc), 'PERM_SETS_FAILED', 500)


@admin_api_bp.route('/permissions/users')
def api_perm_users():
    org = session.get('active_org', 'dev')
    search = request.args.get('q', '').strip()
    try:
        from services import perm_auditor
        data = perm_auditor.get_users(org, search=search)
        return ok(data)
    except Exception as exc:
        logger.exception('perm users failed')
        return error_response(str(exc), 'PERM_USERS_FAILED', 500)


@admin_api_bp.route('/permissions/user/<user_id>')
def api_perm_user_detail(user_id):
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_user_detail(org, user_id)
        return ok(data)
    except Exception as exc:
        logger.exception('perm user detail failed')
        return error_response(str(exc), 'PERM_USER_DETAIL_FAILED', 500)


@admin_api_bp.route('/permissions/set/<pset_id>')
def api_perm_set_detail(pset_id):
    org = session.get('active_org', 'dev')
    try:
        from services import perm_auditor
        data = perm_auditor.get_pset_detail(org, pset_id)
        return ok(data)
    except Exception as exc:
        logger.exception('perm set detail failed')
        return error_response(str(exc), 'PERM_SET_DETAIL_FAILED', 500)


@admin_api_bp.route('/permissions/object-matrix')
def api_perm_object_matrix():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return error_response('object param required', 'INVALID_INPUT', 400)
    try:
        from services import perm_auditor
        data = perm_auditor.get_object_access_matrix(org, object_name)
        return ok(data)
    except Exception as exc:
        logger.exception('perm object matrix failed')
        return error_response(str(exc), 'PERM_OBJECT_MATRIX_FAILED', 500)


@admin_api_bp.route('/permissions/field-matrix')
def api_perm_field_matrix():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return error_response('object param required', 'INVALID_INPUT', 400)
    try:
        from services import perm_auditor
        data = perm_auditor.get_field_access_matrix(org, object_name)
        return ok(data)
    except Exception as exc:
        logger.exception('perm field matrix failed')
        return error_response(str(exc), 'PERM_FIELD_MATRIX_FAILED', 500)


@admin_api_bp.route('/automation/validation-rules')
def api_validation_rules():
    org = session.get('active_org', 'dev')
    try:
        from services import org_automation
        data = org_automation.get_validation_rules(org)
        return ok(data)
    except Exception as exc:
        logger.exception('validation rules failed')
        return error_response(str(exc), 'VALIDATION_RULES_FAILED', 500)


@admin_api_bp.route('/automation/flows')
def api_flows():
    org = session.get('active_org', 'dev')
    try:
        from services import org_automation
        data = org_automation.get_flows(org)
        return ok(data)
    except Exception as exc:
        logger.exception('flows failed')
        return error_response(str(exc), 'FLOWS_FAILED', 500)


@admin_api_bp.route('/automation/triggers')
def api_triggers():
    org = session.get('active_org', 'dev')
    try:
        from services import org_automation
        data = org_automation.get_apex_triggers(org)
        return ok(data)
    except Exception as exc:
        logger.exception('triggers failed')
        return error_response(str(exc), 'TRIGGERS_FAILED', 500)


@admin_api_bp.route('/automation/sharing-model')
def api_sharing_model():
    org = session.get('active_org', 'dev')
    try:
        from services import org_automation
        data = org_automation.get_sharing_model(org)
        return ok(data)
    except Exception as exc:
        logger.exception('sharing model failed')
        return error_response(str(exc), 'SHARING_MODEL_FAILED', 500)


@admin_api_bp.route('/anonymizer/objects', methods=['GET'])
def api_anonymizer_objects():
    try:
        from services import anonymizer
        return ok(anonymizer.list_objects())
    except Exception as exc:
        logger.exception('anonymizer list_objects failed')
        return error_response(str(exc), 'ANONYMIZER_OBJECTS_FAILED', 500)


@admin_api_bp.route('/anonymizer/preview', methods=['POST'])
def api_anonymizer_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    field_names = body.get('fields', [])
    if not object_name:
        return error_response('object is required', 'INVALID_INPUT', 400)
    try:
        from services import anonymizer
        result = anonymizer.preview(org=org, object_name=object_name, field_names=field_names)
        return ok(result)
    except Exception as exc:
        logger.exception('anonymizer preview failed')
        return error_response(str(exc), 'ANONYMIZER_PREVIEW_FAILED', 500)


@admin_api_bp.route('/anonymizer/run', methods=['POST'])
def api_anonymizer_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    field_names = body.get('fields', [])
    dry_run = bool(body.get('dry_run', True))
    if not object_name or not field_names:
        return error_response('object and fields are required', 'INVALID_INPUT', 400)
    try:
        from services import anonymizer
        result = anonymizer.run(org=org, object_name=object_name, field_names=field_names, dry_run=dry_run)
        return ok(result)
    except Exception as exc:
        logger.exception('anonymizer run failed')
        return error_response(str(exc), 'ANONYMIZER_RUN_FAILED', 500)
