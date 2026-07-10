import logging
import re
import time
from typing import Optional

from config import Config
from conductor_provider import get_conductor_client

logger = logging.getLogger(__name__)

_ERROR_PATTERNS = [
    'DUPLICATE_VALUE',
    'FIELD_INTEGRITY_EXCEPTION',
    'REQUIRED_FIELD_MISSING',
    'INVALID_FIELD',
    'TIMEOUT',
]


def extract_sf_error_code(reason: str) -> str:
    """Extract the first recognized SF error code from a workflow failure reason string."""
    for code in _ERROR_PATTERNS:
        if re.search(code, reason, re.IGNORECASE):
            return code
    return 'UNKNOWN'


def get_batch_status(workflow_name: str, start_time_ms: Optional[int] = None) -> dict:
    conductor = get_conductor_client()
    status = conductor.get_batch_status(workflow_name, start_time_ms)
    total = status.get('total', 0) or 1
    done = status.get('completed', 0) + status.get('failed', 0)
    status['progress_pct'] = round(100 * done / total, 1)
    if Config.SHOW_MOCK:
        # Demo rate so the velocity widget shows a plausible ETA in mock mode.
        running = status.get('running', 0)
        queued = status.get('queued', 0)
        rate_per_min = 48
        remaining = running + queued
        status['rate_per_min'] = rate_per_min
        status['eta_minutes'] = round(remaining / rate_per_min, 0) if rate_per_min > 0 else None
    else:
        # Real Conductor status has no throughput field — leave the rate null
        # rather than fabricate one outside of demo mode.
        status['rate_per_min'] = None
        status['eta_minutes'] = None
    return status


def get_failure_reasons(workflow_name: str, start_time_ms: Optional[int] = None) -> dict:
    conductor = get_conductor_client()
    workflows = conductor.search_workflows(workflow_name, 'FAILED', start_time_ms)

    breakdown: dict[str, int] = {}
    sis_ids_by_error: dict[str, list] = {}

    for wf in workflows:
        reason = wf.get('reasonForIncompletion', '') or ''
        code = extract_sf_error_code(reason)
        breakdown[code] = breakdown.get(code, 0) + 1

        # Extract SIS ID from input JSON string
        import json
        try:
            inp = json.loads(wf.get('input', '{}'))
            sis_id = inp.get('sisId', wf.get('workflowId', ''))
        except Exception:
            sis_id = wf.get('workflowId', '')
        sis_ids_by_error.setdefault(code, []).append(sis_id)

    return {
        'breakdown': breakdown,
        'sis_ids_by_error': sis_ids_by_error,
        'total_failures': len(workflows),
    }


def rerun_workflows(workflow_ids: list) -> list:
    conductor = get_conductor_client()
    results = []
    for wf_id in workflow_ids:
        try:
            resp = conductor.retry_workflow(wf_id)
            results.append({
                'workflow_id': wf_id,
                'status_code': resp.get('status_code', 200),
                'success': resp.get('status_code', 200) in (200, 204),
            })
        except Exception as exc:
            logger.error("rerun_workflows: failed to retry %s: %s", wf_id, exc)
            results.append({'workflow_id': wf_id, 'status_code': 500, 'success': False})
        time.sleep(0.1)
    return results
