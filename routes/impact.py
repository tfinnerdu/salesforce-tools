import logging

from flask import Blueprint, jsonify, render_template, request, session

from services import field_impact, perm_auditor, regression_tester

logger = logging.getLogger(__name__)

impact_bp = Blueprint('impact', __name__, url_prefix='/impact')


# ── Page routes ───────────────────────────────────────────────────────────────

@impact_bp.route('/')
@impact_bp.route('')
def index():
    return render_template('impact/index.html')


# ── Field Impact ──────────────────────────────────────────────────────────────

@impact_bp.route('/field-scan')
def api_field_scan():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    field_name = request.args.get('field', '').strip()
    if not object_name or not field_name:
        return jsonify({'success': False, 'data': None, 'error': 'object and field params are required'}), 400
    try:
        result = field_impact.scan_field(org, object_name, field_name)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('field_scan failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


# ── Permission Audit ──────────────────────────────────────────────────────────

@impact_bp.route('/permissions')
def api_permissions():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return jsonify({'success': False, 'data': None, 'error': 'object param is required'}), 400
    try:
        result = perm_auditor.get_field_access(org, object_name)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('permissions audit failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@impact_bp.route('/permissions/field')
def api_permissions_field():
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    field_name = request.args.get('field', '').strip()
    if not object_name or not field_name:
        return jsonify({'success': False, 'data': None, 'error': 'object and field params are required'}), 400
    try:
        result = perm_auditor.summarize_field(org, object_name, field_name)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('permissions field summary failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@impact_bp.route('/assignments')
def api_assignments():
    org = session.get('active_org', 'dev')
    try:
        result = perm_auditor.get_assignments(org)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('assignments query failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


# ── Regression Tests ──────────────────────────────────────────────────────────

@impact_bp.route('/regression', methods=['GET'])
def api_regression_list():
    try:
        suites = regression_tester.list_suites()
        return jsonify({'success': True, 'data': suites})
    except Exception as exc:
        logger.exception('regression list failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@impact_bp.route('/regression', methods=['POST'])
def api_regression_create():
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    assertions = body.get('assertions', [])
    if not name:
        return jsonify({'success': False, 'data': None, 'error': 'name is required'}), 400
    if not isinstance(assertions, list):
        return jsonify({'success': False, 'data': None, 'error': 'assertions must be an array'}), 400
    try:
        suite = regression_tester.save_suite(name, assertions)
        return jsonify({'success': True, 'data': suite}), 201
    except Exception as exc:
        logger.exception('regression create failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@impact_bp.route('/regression/<int:suite_id>/run', methods=['POST'])
def api_regression_run(suite_id: int):
    org = session.get('active_org', 'dev')
    try:
        result = regression_tester.run_suite(org, suite_id)
        return jsonify({'success': True, 'data': result})
    except ValueError as exc:
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 404
    except Exception as exc:
        logger.exception('regression run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@impact_bp.route('/regression/<int:suite_id>/baseline', methods=['POST'])
def api_regression_baseline(suite_id: int):
    org = session.get('active_org', 'dev')
    try:
        result = regression_tester.save_baseline(org, suite_id)
        return jsonify({'success': True, 'data': result})
    except ValueError as exc:
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 404
    except Exception as exc:
        logger.exception('regression baseline failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
