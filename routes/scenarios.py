"""Scenarios blueprint — multi-step Data Ops pipelines + app-level tags.

UI page at ``/scenarios``; API routes hang off the same prefix per the
project convention (the blueprint prefix is the namespace, no /api/v1).
"""
import hmac
import json
import logging

from flask import Blueprint, jsonify, render_template, request, session

from config import Config
from services import scenarios as scenarios_svc
from services import tags as tags_svc

logger = logging.getLogger(__name__)

scenarios_bp = Blueprint('scenarios', __name__, url_prefix='/scenarios')


def _scheduler_authorized() -> bool:
    """True when the request carries the valid scheduler token.

    Scheduled runs are disabled entirely when SCHEDULER_TOKEN is unset — we
    never want an unauthenticated headless trigger of a write pipeline.
    """
    token = Config.SCHEDULER_TOKEN
    if not token:
        return False
    provided = request.headers.get('X-MC-Scheduler-Token', '')
    return bool(provided) and hmac.compare_digest(provided, token)


# ── Page routes ──────────────────────────────────────────────────────────────

@scenarios_bp.route('/')
@scenarios_bp.route('')
def index():
    return render_template('scenarios/index.html')


@scenarios_bp.route('/new')
def new_page():
    return render_template('scenarios/builder.html', scenario_id='new')


@scenarios_bp.route('/<int:scenario_id>')
def builder_page(scenario_id):
    return render_template('scenarios/builder.html', scenario_id=scenario_id)


# ── Scenario CRUD ────────────────────────────────────────────────────────────

@scenarios_bp.route('/list')
def api_list():
    org = request.args.get('org') or session.get('active_org', 'dev')
    try:
        rows = scenarios_svc.list_scenarios(org=org)
        ids = [r['id'] for r in rows]
        tag_map = tags_svc.get_tag_map('scenario', ids) if ids else {}
        for r in rows:
            r['tags'] = tag_map.get(r['id'], [])
        return jsonify({'success': True, 'data': rows})
    except Exception as exc:
        logger.exception('scenarios list failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/get/<int:scenario_id>')
def api_get(scenario_id):
    try:
        row = scenarios_svc.get_scenario(scenario_id)
        if row is None:
            return jsonify({'success': False, 'error': 'Scenario not found'}), 404
        row['tags'] = tags_svc.get_tags_for('scenario', scenario_id)
        return jsonify({'success': True, 'data': row})
    except Exception as exc:
        logger.exception('scenario get failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/create', methods=['POST'])
def api_create():
    body = request.get_json(silent=True) or {}
    org = session.get('active_org', 'dev')
    try:
        row = scenarios_svc.create_scenario(
            name=body.get('name', ''),
            description=body.get('description', ''),
            org=org,
            steps=body.get('steps', []),
            created_by=session.get('user', 'system'),
        )
        return jsonify({'success': True, 'data': row}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('scenario create failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/update/<int:scenario_id>', methods=['POST'])
def api_update(scenario_id):
    body = request.get_json(silent=True) or {}
    try:
        row = scenarios_svc.update_scenario(
            scenario_id=scenario_id,
            name=body.get('name', ''),
            description=body.get('description', ''),
            steps=body.get('steps', []),
        )
        if row is None:
            return jsonify({'success': False, 'error': 'Scenario not found'}), 404
        return jsonify({'success': True, 'data': row})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('scenario update failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>', methods=['DELETE'])
def api_delete(scenario_id):
    try:
        ok = scenarios_svc.delete_scenario(scenario_id)
        if not ok:
            return jsonify({'success': False, 'error': 'Scenario not found'}), 404
        return jsonify({'success': True, 'data': {'deleted': scenario_id}})
    except Exception as exc:
        logger.exception('scenario delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Run ──────────────────────────────────────────────────────────────────────

@scenarios_bp.route('/<int:scenario_id>/run', methods=['POST'])
def api_run(scenario_id):
    """Execute every step in order. Synchronous — returns once the run finishes.

    The UI gates this endpoint through MC.confirm (data-mc-confirm-ack on the
    Run button), so by the time this fires the user has explicitly opted into
    the writes the scenario performs.
    """
    org = session.get('active_org', 'dev')
    try:
        result = scenarios_svc.run_scenario(scenario_id, org)
        return jsonify({'success': True, 'data': result})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('scenario run failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>/runs')
def api_run_history(scenario_id):
    try:
        rows = scenarios_svc.list_runs(scenario_id)
        return jsonify({'success': True, 'data': rows})
    except Exception as exc:
        logger.exception('scenario run history failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Scheduling (Argo) ─────────────────────────────────────────────────────────

@scenarios_bp.route('/<int:scenario_id>/approve', methods=['POST'])
def api_set_approved(scenario_id):
    """Set/clear the manual sign-off that lets a scenario be scheduled."""
    body = request.get_json(silent=True) or {}
    approved = bool(body.get('approved', False))
    try:
        row = scenarios_svc.set_schedule_approved(scenario_id, approved)
        if row is None:
            return jsonify({'success': False, 'error': 'Scenario not found'}), 404
        return jsonify({'success': True, 'data': row})
    except Exception as exc:
        logger.exception('scenario approve failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>/argo-manifest', methods=['POST'])
def api_argo_manifest(scenario_id):
    """Generate an Argo CronWorkflow YAML for this scenario + cron schedule."""
    body = request.get_json(silent=True) or {}
    scenario = scenarios_svc.get_scenario(scenario_id)
    if scenario is None:
        return jsonify({'success': False, 'error': 'Scenario not found'}), 404
    try:
        from services import argo
        manifest = argo.generate_cronworkflow(
            scenario_id, scenario['name'], body.get('schedule', ''))
        return jsonify({'success': True, 'data': {'manifest': manifest}})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('argo manifest generation failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>/scheduled-run', methods=['POST'])
def api_scheduled_run(scenario_id):
    """Token-authed headless trigger for Argo. Runs an *approved* scenario and
    logs a structured summary to stdout (the Argo-visible notification).

    A non-clean run returns HTTP 500 so ``curl -f`` fails and the CronWorkflow
    is flagged in the Argo UI; the body + log line carry the per-step detail.
    """
    if not _scheduler_authorized():
        return jsonify({'success': False, 'error': 'Unauthorized scheduled trigger',
                        'code': 'SCHEDULER_UNAUTHORIZED'}), 401
    scenario = scenarios_svc.get_scenario(scenario_id)
    if scenario is None:
        return jsonify({'success': False, 'error': 'Scenario not found'}), 404
    if not scenario.get('schedule_approved'):
        return jsonify({
            'success': False,
            'error': 'Scenario is not approved for scheduled runs. Approve it '
                     'in the builder after testing it interactively.',
            'code': 'NOT_SCHEDULE_APPROVED',
        }), 403

    org = scenario.get('org') or Config.DEFAULT_ORG
    try:
        result = scenarios_svc.run_scenario(scenario_id, org)
    except Exception as exc:
        logger.info(json.dumps({
            'event': 'scheduled_scenario_run', 'scenario_id': scenario_id,
            'scenario': scenario.get('name'), 'org': org,
            'status': 'error', 'error': str(exc),
        }))
        return jsonify({'success': False, 'error': str(exc)}), 500

    # One structured stdout line — Argo captures it; this is the notification.
    logger.info(json.dumps({
        'event': 'scheduled_scenario_run',
        'scenario_id': scenario_id, 'scenario': scenario.get('name'), 'org': org,
        'run_id': result.get('run_id'), 'status': result.get('status'),
        'steps': len(result.get('step_results') or []),
        'failed_steps': sum(1 for s in (result.get('step_results') or [])
                            if s.get('status') == 'failed'),
    }))
    http = 200 if result.get('status') == 'success' else 500
    return jsonify({'success': result.get('status') == 'success', 'data': result}), http


# ── Tags ─────────────────────────────────────────────────────────────────────

@scenarios_bp.route('/tags')
def api_tags_list():
    try:
        return jsonify({'success': True, 'data': tags_svc.list_tags()})
    except Exception as exc:
        logger.exception('tags list failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/tags', methods=['POST'])
def api_tags_create():
    body = request.get_json(silent=True) or {}
    try:
        row = tags_svc.create_tag(
            name=body.get('name', ''),
            color=body.get('color', 'slate'),
        )
        return jsonify({'success': True, 'data': row}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('tag create failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def api_tags_delete(tag_id):
    try:
        ok = tags_svc.delete_tag(tag_id)
        return jsonify({'success': ok, 'data': {'deleted': tag_id}})
    except Exception as exc:
        logger.exception('tag delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>/tags/<int:tag_id>', methods=['POST'])
def api_attach_tag(scenario_id, tag_id):
    try:
        tags_svc.attach_tag(tag_id, 'scenario', scenario_id)
        return jsonify({'success': True, 'data': {'attached': tag_id}})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('tag attach failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@scenarios_bp.route('/<int:scenario_id>/tags/<int:tag_id>', methods=['DELETE'])
def api_detach_tag(scenario_id, tag_id):
    try:
        ok = tags_svc.detach_tag(tag_id, 'scenario', scenario_id)
        return jsonify({'success': ok})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('tag detach failed')
        return jsonify({'success': False, 'error': str(exc)}), 500
