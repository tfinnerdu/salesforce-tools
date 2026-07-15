import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from services import duplicate_radar, external_id_coverage, contactpoint_scanner, field_completeness, orphan_scanner
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to validation_api_bp under
# /api/v1/validation; the old /validation/<subpath> paths 308-redirect there
# (register_legacy_json_redirect below) so existing MC.api('/validation/...')
# calls keep working unmodified.
validation_bp = Blueprint('validation', __name__, url_prefix='/validation')
validation_api_bp = Blueprint('validation_api', __name__, url_prefix='/api/v1/validation')


@validation_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@validation_bp.route('/')
@validation_bp.route('')
def index():
    return redirect(url_for('validation.duplicates'))


@validation_bp.route('/duplicates')
def duplicates():
    return render_template('validation/duplicate_radar.html')


@validation_bp.route('/external-ids')
def external_ids():
    return render_template('validation/external_id.html')


@validation_bp.route('/contactpoints')
def contactpoints():
    return render_template('validation/contactpoint.html')


@validation_bp.route('/completeness')
def completeness():
    return render_template('validation/field_completeness.html')


@validation_bp.route('/orphans')
def orphans():
    return render_template('validation/orphan_scanner.html')


@validation_bp.route('/merge-history')
def merge_history_page():
    return render_template('validation/merge_history.html')


register_legacy_json_redirect(validation_bp, '/api/v1/validation')


# ── API routes ────────────────────────────────────────────────────────────────

@validation_api_bp.route('/duplicates/scan', methods=['POST'])
def api_duplicates_scan():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    try:
        result = duplicate_radar.scan(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('duplicate scan failed')
        return error_response(str(exc), 'DUPLICATES_SCAN_FAILED', 500)


@validation_api_bp.route('/duplicates/merge', methods=['POST'])
def api_duplicates_merge():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    master_id = body.get('master_id')
    victim_id = body.get('victim_id')
    if not master_id or not victim_id:
        return error_response('master_id and victim_id are required', 'INVALID_INPUT', 400)
    bypass = session.get('bypass_triggers', False)
    try:
        result = duplicate_radar.merge(org=org, master_id=master_id, victim_id=victim_id, bypass=bypass)
        return ok(result)
    except Exception as exc:
        logger.exception('duplicate merge failed')
        return error_response(str(exc), 'DUPLICATES_MERGE_FAILED', 500)


@validation_api_bp.route('/external-ids/run', methods=['GET'])
def api_external_ids_run():
    org = session.get('active_org', 'dev')
    try:
        result = external_id_coverage.run(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('external id coverage run failed')
        return error_response(str(exc), 'EXTERNAL_IDS_RUN_FAILED', 500)


@validation_api_bp.route('/contactpoints/scan', methods=['GET'])
def api_contactpoints_scan():
    org = session.get('active_org', 'dev')
    try:
        result = contactpoint_scanner.scan(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('contactpoint scan failed')
        return error_response(str(exc), 'CONTACTPOINTS_SCAN_FAILED', 500)


@validation_api_bp.route('/completeness/run', methods=['GET'])
def api_completeness_run():
    org = session.get('active_org', 'dev')
    try:
        result = field_completeness.run(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('field completeness run failed')
        return error_response(str(exc), 'COMPLETENESS_RUN_FAILED', 500)


@validation_api_bp.route('/orphans/scan', methods=['GET'])
def api_orphans_scan():
    org = session.get('active_org', 'dev')
    try:
        result = orphan_scanner.scan(org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('orphan scan failed')
        return error_response(str(exc), 'ORPHANS_SCAN_FAILED', 500)


@validation_api_bp.route('/merge-history/list', methods=['GET'])
def api_merge_history():
    org = session.get('active_org', 'dev')
    try:
        from services import merge_history
        data = merge_history.list_merges(org=org)
        return ok(data)
    except Exception as exc:
        logger.exception('merge history failed')
        return error_response(str(exc), 'MERGE_HISTORY_FAILED', 500)


@validation_api_bp.route('/merge-history/stats', methods=['GET'])
def api_merge_stats():
    org = session.get('active_org', 'dev')
    try:
        from services import merge_history
        data = merge_history.get_stats(org=org)
        return ok(data)
    except Exception as exc:
        logger.exception('merge stats failed')
        return error_response(str(exc), 'MERGE_STATS_FAILED', 500)
