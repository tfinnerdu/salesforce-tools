import logging

from flask import Blueprint, jsonify, render_template, session

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
