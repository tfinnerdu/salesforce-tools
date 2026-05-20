import logging

from flask import Blueprint, jsonify, render_template, request, session

from services import org_observer, storage_breakdown, sandbox_drift

logger = logging.getLogger(__name__)

observe_bp = Blueprint('observe', __name__, url_prefix='/observe')


@observe_bp.route('/')
@observe_bp.route('')
def index():
    return render_template('observe/index.html')


@observe_bp.route('/limits')
def api_limits():
    org = request.args.get('org') or session.get('active_org', 'dev')
    try:
        data = org_observer.get_limits(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('get_limits failed for org %s', org)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/trends')
def api_trends():
    org = request.args.get('org') or session.get('active_org', 'dev')
    try:
        days = int(request.args.get('days', 30))
    except (ValueError, TypeError):
        days = 30
    try:
        data = org_observer.get_quality_trends(org, days=days)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('get_quality_trends failed for org %s', org)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/record-counts')
def api_record_counts():
    org = request.args.get('org') or session.get('active_org', 'dev')
    try:
        data = storage_breakdown.get_record_counts(org)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('get_record_counts failed for org %s', org)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/sandbox-drift')
def api_sandbox_drift():
    baseline = request.args.get('baseline', 'prod')
    target = request.args.get('target', 'sandbox')
    try:
        data = sandbox_drift.run(baseline_org=baseline, target_org=target)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('sandbox drift failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/cross-org')
def api_cross_org():
    orgs_raw = request.args.get('orgs', 'dev,sandbox')
    orgs = [o.strip() for o in orgs_raw.split(',') if o.strip()]
    if not orgs:
        orgs = ['dev', 'sandbox']
    try:
        data = org_observer.get_cross_org_counts(orgs)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('get_cross_org_counts failed for orgs %s', orgs)
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/thresholds', methods=['GET'])
def api_get_thresholds():
    try:
        data = org_observer.get_thresholds()
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('get thresholds failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/thresholds', methods=['POST'])
def api_set_threshold():
    body = request.get_json(silent=True) or {}
    limit_name = body.get('limit_name', '').strip()
    try:
        amber_pct = float(body.get('amber_pct', 50))
        red_pct   = float(body.get('red_pct', 80))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'data': None, 'error': 'amber_pct and red_pct must be numbers'}), 400
    if not limit_name:
        return jsonify({'success': False, 'data': None, 'error': 'limit_name required'}), 400
    if not (0 < amber_pct < red_pct <= 100):
        return jsonify({'success': False, 'data': None, 'error': 'amber_pct must be < red_pct and both 0–100'}), 400
    try:
        data = org_observer.set_threshold(limit_name=limit_name, amber_pct=amber_pct, red_pct=red_pct)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('set threshold failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@observe_bp.route('/thresholds/<limit_name>', methods=['DELETE'])
def api_delete_threshold(limit_name):
    try:
        ok = org_observer.delete_threshold(limit_name)
        return jsonify({'success': True, 'data': {'deleted': ok}})
    except Exception as exc:
        logger.exception('delete threshold failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
