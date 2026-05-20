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
