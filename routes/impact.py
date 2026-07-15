import logging

from flask import Blueprint, render_template, request, session

from services import field_impact, perm_auditor, regression_tester
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to impact_api_bp under
# /api/v1/impact; the old /impact/<subpath> paths 308-redirect there
# (register_legacy_json_redirect below) so existing MC.api('/impact/...')
# calls keep working unmodified.
impact_bp = Blueprint('impact', __name__, url_prefix='/impact')
impact_api_bp = Blueprint('impact_api', __name__, url_prefix='/api/v1/impact')


@impact_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@impact_bp.route('/')
@impact_bp.route('')
def index():
    return render_template('impact/index.html')


register_legacy_json_redirect(impact_bp, '/api/v1/impact')


# ── Field Impact ──────────────────────────────────────────────────────────────

@impact_api_bp.route('/field-scan')
def api_field_scan():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    field_name = request.args.get('field', '').strip()
    if not object_name or not field_name:
        return error_response('object and field params are required', 'INVALID_INPUT', 400)
    try:
        result = field_impact.scan_field(org, object_name, field_name)
        return ok(result)
    except Exception as exc:
        logger.exception('field_scan failed')
        return error_response(str(exc), 'FIELD_SCAN_FAILED', 500)


# ── Permission Audit ──────────────────────────────────────────────────────────

@impact_api_bp.route('/permissions')
def api_permissions():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return error_response('object param is required', 'INVALID_INPUT', 400)
    try:
        result = perm_auditor.get_field_access(org, object_name)
        return ok(result)
    except Exception as exc:
        logger.exception('permissions audit failed')
        return error_response(str(exc), 'PERMISSIONS_FAILED', 500)


@impact_api_bp.route('/permissions/field')
def api_permissions_field():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    field_name = request.args.get('field', '').strip()
    if not object_name or not field_name:
        return error_response('object and field params are required', 'INVALID_INPUT', 400)
    try:
        result = perm_auditor.summarize_field(org, object_name, field_name)
        return ok(result)
    except Exception as exc:
        logger.exception('permissions field summary failed')
        return error_response(str(exc), 'PERMISSIONS_FIELD_FAILED', 500)


@impact_api_bp.route('/assignments')
def api_assignments():
    org = session.get('active_org', 'dev')
    try:
        result = perm_auditor.get_assignments(org)
        return ok(result)
    except Exception as exc:
        logger.exception('assignments query failed')
        return error_response(str(exc), 'ASSIGNMENTS_FAILED', 500)


# ── Regression Tests ──────────────────────────────────────────────────────────

@impact_api_bp.route('/regression', methods=['GET'])
def api_regression_list():
    try:
        suites = regression_tester.list_suites()
        return ok(suites)
    except Exception as exc:
        logger.exception('regression list failed')
        return error_response(str(exc), 'REGRESSION_LIST_FAILED', 500)


@impact_api_bp.route('/regression', methods=['POST'])
def api_regression_create():
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    assertions = body.get('assertions', [])
    if not name:
        return error_response('name is required', 'NAME_REQUIRED', 400)
    if not isinstance(assertions, list):
        return error_response('assertions must be an array', 'INVALID_ASSERTIONS', 400)
    try:
        suite = regression_tester.save_suite(name, assertions)
        return ok(suite, 201)
    except Exception as exc:
        logger.exception('regression create failed')
        return error_response(str(exc), 'REGRESSION_CREATE_FAILED', 500)


@impact_api_bp.route('/regression/<int:suite_id>/run', methods=['POST'])
def api_regression_run(suite_id: int):
    org = session.get('active_org', 'dev')
    try:
        result = regression_tester.run_suite(org, suite_id)
        return ok(result)
    except ValueError as exc:
        return error_response(str(exc), 'NOT_FOUND', 404)
    except Exception as exc:
        logger.exception('regression run failed')
        return error_response(str(exc), 'REGRESSION_RUN_FAILED', 500)


@impact_api_bp.route('/regression/<int:suite_id>/baseline', methods=['POST'])
def api_regression_baseline(suite_id: int):
    org = session.get('active_org', 'dev')
    try:
        result = regression_tester.save_baseline(org, suite_id)
        return ok(result)
    except ValueError as exc:
        return error_response(str(exc), 'NOT_FOUND', 404)
    except Exception as exc:
        logger.exception('regression baseline failed')
        return error_response(str(exc), 'REGRESSION_BASELINE_FAILED', 500)


# ── Permission Set Gap Analysis ───────────────────────────────────────────────

@impact_api_bp.route('/perm-gap/list')
def api_perm_gap_list():
    org = session.get('active_org', 'dev')
    try:
        from services import perm_gap_analyzer
        data = perm_gap_analyzer.list_permission_sets(org)
        return ok(data)
    except Exception as exc:
        logger.exception('perm gap list failed')
        return error_response(str(exc), 'PERM_GAP_LIST_FAILED', 500)


@impact_api_bp.route('/perm-gap/compare', methods=['POST'])
def api_perm_gap_compare():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    ps_a = body.get('ps_a', '').strip()
    ps_b = body.get('ps_b', '').strip()
    if not ps_a or not ps_b:
        return error_response('ps_a and ps_b required', 'INVALID_INPUT', 400)
    if ps_a == ps_b:
        return error_response('Select two different permission sets', 'SAME_PERMISSION_SET', 400)
    try:
        from services import perm_gap_analyzer
        data = perm_gap_analyzer.compare(org=org, ps_id_a=ps_a, ps_id_b=ps_b)
        return ok(data)
    except Exception as exc:
        logger.exception('perm gap compare failed')
        return error_response(str(exc), 'PERM_GAP_COMPARE_FAILED', 500)
