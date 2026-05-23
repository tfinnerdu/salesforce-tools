import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from conductor_provider import get_conductor_client
from services.batch_tracker import extract_sf_error_code

logger = logging.getLogger(__name__)

_ERROR_META = {
    'DUPLICATE_VALUE': {
        'label': 'Duplicate External ID',
        'cause': 'Multiple records sharing same external ID',
        'suggested_fix': 'Run Duplicate Radar scan, merge or remove extra records, then retry',
        'severity': 'high',
    },
    'FIELD_INTEGRITY_EXCEPTION': {
        'label': 'Field Integrity Exception',
        'cause': 'Parent record (Individual/Account) not created before child ContactPoint',
        'suggested_fix': (
            'Ensure Individual upsert task runs before ContactPoint tasks in Conductor workflow'
        ),
        'severity': 'high',
    },
    'REQUIRED_FIELD_MISSING': {
        'label': 'Required Field Missing',
        'cause': 'Required field is blank in source Colleague data',
        'suggested_fix': (
            'Fix source data in Colleague or add default value in Conductor transform'
        ),
        'severity': 'high',
    },
    'TIMEOUT': {
        'label': 'Conductor Timeout',
        'cause': 'Conductor worker timeout — transient',
        'suggested_fix': 'Retry — these are safe to re-run immediately',
        'severity': 'low',
    },
    'INVALID_FIELD': {
        'label': 'Invalid Field API Name',
        'cause': "Field API name in Conductor mapping doesn't exist in org",
        'suggested_fix': (
            'Check org schema, update Conductor workflow mapping to match current field API names'
        ),
        'severity': 'medium',
    },
    'UNKNOWN': {
        'label': 'Unknown Error',
        'cause': 'Unrecognized error',
        'suggested_fix': 'View full workflow detail for manual investigation',
        'severity': 'medium',
    },
}


def categorize_conductor_failures(workflow_name: str, hours_back: int = 24) -> list:
    conductor = get_conductor_client()
    start_ms = int((datetime.utcnow() - timedelta(hours=hours_back)).timestamp() * 1000)
    workflows = conductor.search_workflows(workflow_name, 'FAILED', start_ms)

    categories: dict = {}

    for wf in workflows:
        reason = wf.get('reasonForIncompletion', '') or ''
        code = extract_sf_error_code(reason)

        try:
            inp = json.loads(wf.get('input', '{}'))
            sis_id = inp.get('sisId', '')
        except Exception:
            sis_id = ''

        wf_id = wf.get('workflowId', '')

        if code not in categories:
            meta = _ERROR_META.get(code, _ERROR_META['UNKNOWN'])
            categories[code] = {
                'error_code': code,
                'count': 0,
                'sis_ids': [],
                'workflow_ids': [],
                'label': meta['label'],
                'cause': meta['cause'],
                'suggested_fix': meta['suggested_fix'],
                'severity': meta['severity'],
            }
        categories[code]['count'] += 1
        if sis_id:
            categories[code]['sis_ids'].append(sis_id)
        if wf_id:
            categories[code]['workflow_ids'].append(wf_id)

    return sorted(categories.values(), key=lambda c: c['count'], reverse=True)


def requeue_batch(batch_id: str, org: str) -> dict:
    """Requeue a failed Conductor batch.

    With SHOW_MOCK=true, returns a synthesized "queued" success so the demo UI
    is end-to-end. With SHOW_MOCK=false, raises — the Conductor client has no
    batch-level requeue endpoint yet, and we never fabricate success in real
    mode. Retry the individual failed workflows via /migration/reconciler/rerun.
    """
    if Config.SHOW_MOCK:
        return {
            'status': 'queued',
            'batch_id': batch_id,
            'message': f'Batch {batch_id} requeued successfully',
        }
    raise RuntimeError(
        f"Batch requeue is not available — the Conductor client has no "
        f"batch-level requeue endpoint (batch_id={batch_id}, org={org}). "
        f"Retry the individual failed workflows via /migration/reconciler/rerun."
    )


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
