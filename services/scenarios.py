"""Scenarios — saved multi-step Data Ops pipelines.

A scenario is an ordered list of steps. Each step is one Data Ops operation
(delete / modify / reassign / bulk_update / tune) with its parameters. Running
a scenario dispatches each step to the existing services in sequence and
collects per-step results. Steps that fail can either stop the pipeline
(``on_error='stop'``, default) or continue (``on_error='continue'``).

The confirmation UX is upstream: the UI's Run button gates the whole pipeline
through MC.confirm before this service is reached, so by the time
``run_scenario`` is called the user has already acknowledged the writes.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from db import db_available, get_cursor

logger = logging.getLogger(__name__)

# Step types this runner knows how to dispatch. Each maps to a (service_module,
# function_name, required_params, optional_params) tuple — the dispatcher uses
# this both to validate scenarios on save and to execute them.
_VALID_STEP_TYPES = {
    'delete', 'modify', 'reassign', 'bulk_update', 'tune', 'key_map_expand',
}

_REQUIRED_PARAMS = {
    'delete':         {'object', 'where_clause'},
    'modify':         {'object', 'where_clause', 'field', 'value'},
    'reassign':       {'object', 'where_clause', 'new_owner_id'},
    'bulk_update':    {'object', 'where_clause', 'field', 'value'},
    'tune':           {'object', 'where_clause', 'field_rules'},
    'key_map_expand': {'key_map_id', 'source'},
}


# ── CRUD ─────────────────────────────────────────────────────────────────────

def validate_steps(steps: list) -> list:
    """Raise ValueError for unrecognised step types or missing required params.

    Returns the steps list unchanged on success — callers may chain.
    """
    if not isinstance(steps, list):
        raise ValueError('steps must be a list')
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f'Step {i}: expected an object, got {type(step).__name__}')
        step_type = step.get('type', '').strip()
        if step_type not in _VALID_STEP_TYPES:
            raise ValueError(
                f'Step {i}: unknown step type {step_type!r} — '
                f'must be one of {sorted(_VALID_STEP_TYPES)}'
            )
        params = step.get('params') or {}
        if not isinstance(params, dict):
            raise ValueError(f'Step {i}: params must be an object')
        missing = _REQUIRED_PARAMS[step_type] - set(params)
        if missing:
            raise ValueError(
                f'Step {i} ({step_type}): missing required params {sorted(missing)}'
            )
    return steps


def list_scenarios(org: Optional[str] = None) -> list:
    """Return all scenarios, optionally filtered by org. Newest first."""
    if not db_available():
        return []
    sql = (
        'SELECT id, name, description, org, steps_json, created_by, '
        '       created_at, updated_at '
        'FROM scenarios '
    )
    params: list = []
    if org:
        sql += 'WHERE org = %s '
        params.append(org)
    sql += 'ORDER BY updated_at DESC'
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_serialize(r) for r in rows]


def get_scenario(scenario_id: int) -> Optional[dict]:
    """Return one scenario or None when missing / DB unavailable."""
    if not db_available():
        return None
    with get_cursor() as cur:
        cur.execute(
            'SELECT id, name, description, org, steps_json, created_by, '
            '       created_at, updated_at '
            'FROM scenarios WHERE id = %s',
            (scenario_id,),
        )
        row = cur.fetchone()
    return _serialize(row) if row else None


def create_scenario(name: str, description: str, org: str, steps: list,
                    created_by: str = 'system') -> dict:
    """Insert a new scenario; returns the saved record."""
    if not name or not name.strip():
        raise ValueError('Scenario name is required')
    validate_steps(steps)
    if not db_available():
        raise RuntimeError('Scenarios require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO scenarios (name, description, org, steps_json, created_by) '
            'VALUES (%s, %s, %s, %s, %s) '
            'RETURNING id, name, description, org, steps_json, created_by, '
            '          created_at, updated_at',
            (name.strip(), description, org, json.dumps(steps), created_by),
        )
        row = cur.fetchone()
    return _serialize(row)


def update_scenario(scenario_id: int, name: str, description: str,
                    steps: list) -> Optional[dict]:
    """Update an existing scenario. Returns None when no row matched."""
    if not name or not name.strip():
        raise ValueError('Scenario name is required')
    validate_steps(steps)
    if not db_available():
        raise RuntimeError('Scenarios require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'UPDATE scenarios '
            'SET name = %s, description = %s, steps_json = %s, updated_at = NOW() '
            'WHERE id = %s '
            'RETURNING id, name, description, org, steps_json, created_by, '
            '          created_at, updated_at',
            (name.strip(), description, json.dumps(steps), scenario_id),
        )
        row = cur.fetchone()
    return _serialize(row) if row else None


def delete_scenario(scenario_id: int) -> bool:
    """Delete one scenario. Returns True on success."""
    if not db_available():
        raise RuntimeError('Scenarios require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM scenarios WHERE id = %s', (scenario_id,))
        return cur.rowcount > 0


# ── Run history ──────────────────────────────────────────────────────────────

def list_runs(scenario_id: int, limit: int = 20) -> list:
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            'SELECT id, scenario_id, org, started_at, finished_at, status, step_results '
            'FROM scenario_runs WHERE scenario_id = %s '
            'ORDER BY started_at DESC LIMIT %s',
            (scenario_id, limit),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ── Run ──────────────────────────────────────────────────────────────────────

def run_scenario(scenario_id: int, org: str) -> dict:
    """Execute every step in order, recording per-step results.

    Returns {run_id, status, step_results}. ``status`` is one of:
      - 'success'  — every step succeeded
      - 'partial'  — at least one step failed but on_error='continue' was set
      - 'failed'   — a step failed and on_error='stop' (default) aborted the run

    Each step's handler is the same service the Data Ops tab calls directly,
    so the same SHOW_MOCK behavior, dml_guard, and audit semantics apply.
    """
    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise ValueError(f'Scenario {scenario_id} not found')
    steps = scenario.get('steps') or []
    if not steps:
        raise ValueError(f'Scenario {scenario_id} has no steps')

    run_id = _start_run(scenario_id, org)
    step_results: list = []
    overall_status = 'success'

    for i, step in enumerate(steps, start=1):
        step_type = step.get('type', '')
        params = step.get('params') or {}
        on_error = step.get('on_error', 'stop')
        started = datetime.now(timezone.utc).isoformat()
        try:
            detail = _dispatch_step(step_type, org, params)
            result = {
                'step_index': i,
                'step_type': step_type,
                'status': 'success',
                'detail': detail,
                'started_at': started,
                'finished_at': datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.exception('scenario %s step %s (%s) failed', scenario_id, i, step_type)
            result = {
                'step_index': i,
                'step_type': step_type,
                'status': 'failed',
                'detail': {'error': str(exc)},
                'started_at': started,
                'finished_at': datetime.now(timezone.utc).isoformat(),
            }
            step_results.append(result)
            if on_error == 'continue':
                overall_status = 'partial'
                continue
            overall_status = 'failed'
            _finish_run(run_id, overall_status, step_results)
            return {'run_id': run_id, 'status': overall_status, 'step_results': step_results}
        step_results.append(result)

    _finish_run(run_id, overall_status, step_results)
    return {'run_id': run_id, 'status': overall_status, 'step_results': step_results}


def _dispatch_step(step_type: str, org: str, params: dict) -> dict:
    """Call the appropriate Data Ops service for one step."""
    bypass = bool(params.get('bypass_triggers', False))

    if step_type == 'delete':
        from services import bulk_ops
        return bulk_ops.bulk_delete_execute(
            org, params['object'], params['where_clause'], bypass,
        )
    if step_type == 'modify':
        from services import bulk_ops
        return bulk_ops.bulk_modify_execute(
            org, params['object'], params['where_clause'],
            params['field'], params['value'], bypass,
        )
    if step_type == 'reassign':
        from services import bulk_ops
        return bulk_ops.bulk_reassign_execute(
            org, params['object'], params['where_clause'],
            params['new_owner_id'], bypass,
        )
    if step_type == 'bulk_update':
        from services import bulk_dml
        return bulk_dml.bulk_update(
            org, params['object'], params['where_clause'],
            params['field'], params['value'],
            dry_run=bool(params.get('dry_run', False)),
            bypass_triggers=bypass,
        )
    if step_type == 'tune':
        from services import data_tuner
        return data_tuner.apply_tune(
            org, params['object'], params['where_clause'],
            params['field_rules'], bypass_triggers=bypass,
        )
    if step_type == 'key_map_expand':
        # Preview-only: ingest source rows, expand them through the key_map,
        # persist the full result to key_map_runs, and return just the summary
        # so the scenario_runs row stays small. (No Salesforce writes — the
        # upsert phase is deliberately out of scope until the external-ID
        # field exists on the target SObject.)
        from services import ingest, key_map
        source_rows = ingest.load_source_rows(params['source'], org)
        result = key_map.resolve_and_expand(params['key_map_id'], source_rows, org)
        run_id = key_map.save_run(params['key_map_id'], org, result)
        summary = dict(result['summary'])
        summary['key_map_run_id'] = run_id
        return summary
    raise ValueError(f'Unknown step type: {step_type!r}')


# ── Helpers ──────────────────────────────────────────────────────────────────

def _start_run(scenario_id: int, org: str) -> Optional[int]:
    if not db_available():
        return None
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO scenario_runs (scenario_id, org, status) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (scenario_id, org),
        )
        row = cur.fetchone()
    return row['id'] if row else None


def _finish_run(run_id: Optional[int], status: str, step_results: list) -> None:
    if run_id is None or not db_available():
        return
    with get_cursor() as cur:
        cur.execute(
            'UPDATE scenario_runs '
            'SET status = %s, finished_at = NOW(), step_results = %s '
            'WHERE id = %s',
            (status, json.dumps(step_results), run_id),
        )


def _serialize(row) -> dict:
    """Normalize a DB row into a plain dict with ``steps`` parsed from JSONB."""
    if row is None:
        return None
    d = dict(row)
    raw = d.pop('steps_json', None)
    if isinstance(raw, str):
        try:
            d['steps'] = json.loads(raw)
        except json.JSONDecodeError:
            d['steps'] = []
    else:
        d['steps'] = raw or []
    return d
