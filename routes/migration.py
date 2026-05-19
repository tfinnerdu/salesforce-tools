import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import readiness_validator, batch_tracker, error_reconciler

logger = logging.getLogger(__name__)

migration_bp = Blueprint('migration', __name__, url_prefix='/migration')


# ── Page routes ──────────────────────────────────────────────────────────────

@migration_bp.route('/')
@migration_bp.route('')
def index():
    return redirect(url_for('migration.readiness'))


@migration_bp.route('/readiness')
def readiness():
    return render_template('migration/readiness.html')


@migration_bp.route('/batch')
def batch():
    return render_template('migration/batch_progress.html')


@migration_bp.route('/reconciler')
def reconciler():
    return render_template('migration/error_reconciler.html')


# ── API routes ────────────────────────────────────────────────────────────────

@migration_bp.route('/readiness/run', methods=['POST'])
def api_readiness_run():
    org = session.get('active_org', 'dev')
    try:
        result = readiness_validator.run_full_readiness_check(org)
        readiness_validator.save_run(org, result)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('readiness run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@migration_bp.route('/readiness/history', methods=['GET'])
def api_readiness_history():
    org = session.get('active_org', 'dev')
    try:
        history = readiness_validator.get_history(org, limit=30)
        return jsonify({'success': True, 'data': history})
    except Exception as exc:
        logger.exception('readiness history failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@migration_bp.route('/batch/status', methods=['GET'])
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
        return jsonify({'success': True, 'data': {'status': status, 'failures': failures}})
    except Exception as exc:
        logger.exception('batch status failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@migration_bp.route('/batch/rerun', methods=['POST'])
def api_batch_rerun():
    body = request.get_json(silent=True) or {}
    workflow_ids = body.get('ids', body.get('workflow_ids', []))
    if not workflow_ids:
        return jsonify({'success': False, 'data': None, 'error': 'workflow_ids is required'}), 400
    try:
        result = batch_tracker.rerun_workflows(workflow_ids)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('batch rerun failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@migration_bp.route('/reconciler/errors', methods=['GET'])
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
        return jsonify({'success': True, 'data': categories})
    except Exception as exc:
        logger.exception('reconciler errors failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@migration_bp.route('/reconciler/rerun', methods=['POST'])
def api_reconciler_rerun():
    body = request.get_json(silent=True) or {}
    workflow_ids = body.get('sis_ids', body.get('workflow_ids', []))
    if not workflow_ids:
        return jsonify({'success': False, 'data': None, 'error': 'workflow_ids is required'}), 400
    try:
        result = error_reconciler.rerun_workflows(workflow_ids)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('reconciler rerun failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
