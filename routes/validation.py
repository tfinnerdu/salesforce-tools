import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import duplicate_radar, external_id_coverage, contactpoint_scanner

logger = logging.getLogger(__name__)

validation_bp = Blueprint('validation', __name__, url_prefix='/validation')


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


# ── API routes ────────────────────────────────────────────────────────────────

@validation_bp.route('/duplicates/scan', methods=['POST'])
def api_duplicates_scan():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    try:
        result = duplicate_radar.scan(org=org)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('duplicate scan failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@validation_bp.route('/duplicates/merge', methods=['POST'])
def api_duplicates_merge():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    master_id = body.get('master_id')
    victim_id = body.get('victim_id')
    if not master_id or not victim_id:
        return jsonify({'success': False, 'data': None, 'error': 'master_id and victim_id are required'}), 400
    try:
        result = duplicate_radar.merge(org=org, master_id=master_id, victim_id=victim_id)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('duplicate merge failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@validation_bp.route('/external-ids/run', methods=['GET'])
def api_external_ids_run():
    org = session.get('active_org', 'dev')
    try:
        result = external_id_coverage.run(org=org)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('external id coverage run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@validation_bp.route('/contactpoints/scan', methods=['GET'])
def api_contactpoints_scan():
    org = session.get('active_org', 'dev')
    try:
        result = contactpoint_scanner.scan(org=org)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('contactpoint scan failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
