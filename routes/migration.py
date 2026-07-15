import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from services import readiness_validator, batch_tracker, error_reconciler, preflight_checklist
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes moved to migration_api_bp under
# /api/v1/migration; the old /migration/<subpath> paths 308-redirect there
# (register_legacy_json_redirect below) so existing MC.api('/migration/...')
# calls keep working unmodified.
migration_bp = Blueprint('migration', __name__, url_prefix='/migration')
migration_api_bp = Blueprint('migration_api', __name__, url_prefix='/api/v1/migration')


@migration_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ──────────────────────────────────────────────────────────────

@migration_bp.route('/')
@migration_bp.route('')
def index():
    return redirect(url_for('migration.readiness'))


@migration_bp.route('/readiness')
def readiness():
    return render_template('migration/readiness.html')


@migration_bp.route('/batch')
@migration_bp.route('/batches')
def batch():
    return render_template('migration/batch_progress.html')


@migration_bp.route('/reconciler')
@migration_bp.route('/errors')
def reconciler():
    return render_template('migration/error_reconciler.html')


@migration_bp.route('/velocity')
def page_velocity():
    return render_template('migration/velocity.html')


@migration_bp.route('/preflight')
def preflight():
    return render_template('migration/preflight.html')


register_legacy_json_redirect(migration_bp, '/api/v1/migration')


# ── API routes ────────────────────────────────────────────────────────────────

@migration_api_bp.route('/readiness/run', methods=['POST'])
def api_readiness_run():
    org = session.get('active_org', 'dev')
    try:
        result = readiness_validator.run_full_readiness_check(org)
        readiness_validator.save_run(org, result)
        return ok(result)
    except Exception as exc:
        logger.exception('readiness run failed')
        return error_response(str(exc), 'READINESS_RUN_FAILED', 500)


@migration_api_bp.route('/readiness/history', methods=['GET'])
def api_readiness_history():
    org = session.get('active_org', 'dev')
    try:
        history = readiness_validator.get_history(org, limit=30)
        return ok(history)
    except Exception as exc:
        logger.exception('readiness history failed')
        return error_response(str(exc), 'READINESS_HISTORY_FAILED', 500)


@migration_api_bp.route('/batches/recent', methods=['GET'])
def api_batches_recent():
    """Recent migration batches — consumed by the dashboard Batches widget."""
    org = session.get('active_org', 'dev')
    try:
        from services import migration_velocity
        data = migration_velocity.list_recent_batches(org)
        return ok(data)
    except Exception as exc:
        logger.exception('recent batches failed')
        return error_response(str(exc), 'BATCHES_RECENT_FAILED', 500)


@migration_api_bp.route('/batch/status', methods=['GET'])
def api_batch_status():
    workflow_name = request.args.get('workflow_name', '')
    start_time_ms = request.args.get('start_time_ms')
    if start_time_ms is not None:
        try:
            start_time_ms = int(start_time_ms)
        except ValueError:
            start_time_ms = None
    try:
        status = batch_tracker.get_batch_status(
            workflow_name=workflow_name,
            start_time_ms=start_time_ms,
        )
        failures = batch_tracker.get_failure_reasons(
            workflow_name=workflow_name,
            start_time_ms=start_time_ms,
        )
        return ok({'status': status, 'failures': failures})
    except Exception as exc:
        logger.exception('batch status failed')
        return error_response(str(exc), 'BATCH_STATUS_FAILED', 500)


@migration_api_bp.route('/batch/rerun', methods=['POST'])
def api_batch_rerun():
    body = request.get_json(silent=True) or {}
    workflow_ids = body.get('ids', body.get('workflow_ids', []))
    if not workflow_ids:
        return error_response('workflow_ids is required', 'INVALID_INPUT', 400)
    try:
        result = batch_tracker.rerun_workflows(workflow_ids)
        return ok(result)
    except Exception as exc:
        logger.exception('batch rerun failed')
        return error_response(str(exc), 'BATCH_RERUN_FAILED', 500)


@migration_api_bp.route('/reconciler/errors', methods=['GET'])
def api_reconciler_errors():
    workflow_name = request.args.get('workflow_name', '')
    hours_back = request.args.get('hours_back', 24)
    try:
        hours_back = int(hours_back)
    except (ValueError, TypeError):
        hours_back = 24
    try:
        categories = error_reconciler.categorize_conductor_failures(
            workflow_name=workflow_name,
            hours_back=hours_back,
        )
        return ok(categories)
    except Exception as exc:
        logger.exception('reconciler errors failed')
        return error_response(str(exc), 'RECONCILER_ERRORS_FAILED', 500)


@migration_api_bp.route('/errors/requeue', methods=['POST'])
def api_requeue_batch():
    body = request.get_json(silent=True) or {}
    batch_id = body.get('batch_id', '').strip()
    if not batch_id:
        return error_response('batch_id required', 'INVALID_INPUT', 400)
    org = session.get('active_org', 'dev')
    try:
        result = error_reconciler.requeue_batch(batch_id=batch_id, org=org)
        return ok(result)
    except Exception as exc:
        logger.exception('requeue failed for batch %s', batch_id)
        return error_response(str(exc), 'REQUEUE_BATCH_FAILED', 500)


@migration_api_bp.route('/reconciler/rerun', methods=['POST'])
def api_reconciler_rerun():
    body = request.get_json(silent=True) or {}
    workflow_ids = body.get('sis_ids', body.get('workflow_ids', []))
    if not workflow_ids:
        return error_response('workflow_ids is required', 'INVALID_INPUT', 400)
    try:
        result = error_reconciler.rerun_workflows(workflow_ids)
        return ok(result)
    except Exception as exc:
        logger.exception('reconciler rerun failed')
        return error_response(str(exc), 'RECONCILER_RERUN_FAILED', 500)


@migration_api_bp.route('/velocity/data', methods=['GET'])
def api_velocity_data():
    org = session.get('active_org', 'dev')
    try:
        days = int(request.args.get('days', 30))
    except (ValueError, TypeError):
        days = 30
    try:
        from services import migration_velocity
        data = migration_velocity.get_velocity_data(org=org, days=days)
        return ok(data)
    except Exception as exc:
        logger.exception('velocity data failed')
        return error_response(str(exc), 'VELOCITY_DATA_FAILED', 500)


@migration_api_bp.route('/preflight/items', methods=['GET'])
def api_preflight_items():
    org = session.get('active_org', 'dev')
    try:
        preflight_checklist._ensure_table()
        preflight_checklist.seed_defaults(org)
        data = preflight_checklist.list_items(org)
        return ok(data)
    except Exception as exc:
        logger.exception('preflight list failed')
        return error_response(str(exc), 'PREFLIGHT_ITEMS_FAILED', 500)


@migration_api_bp.route('/preflight/toggle', methods=['POST'])
def api_preflight_toggle():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    item_id = body.get('id')
    checked = bool(body.get('checked', False))
    if item_id is None:
        return error_response('id required', 'INVALID_INPUT', 400)
    try:
        result = preflight_checklist.toggle_item(org=org, item_id=int(item_id), checked=checked)
        return ok(result)
    except Exception as exc:
        logger.exception('preflight toggle failed')
        return error_response(str(exc), 'PREFLIGHT_TOGGLE_FAILED', 500)


@migration_api_bp.route('/preflight/progress', methods=['GET'])
def api_preflight_progress():
    org = session.get('active_org', 'dev')
    try:
        data = preflight_checklist.get_progress(org)
        return ok(data)
    except Exception as exc:
        logger.exception('preflight progress failed')
        return error_response(str(exc), 'PREFLIGHT_PROGRESS_FAILED', 500)
