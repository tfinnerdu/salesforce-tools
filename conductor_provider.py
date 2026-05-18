"""Conductor provider — returns real ConductorClient or a mock."""
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


# ── env gate ──────────────────────────────────────────────────────────────────

def _configured() -> bool:
    """Return True when real Conductor credentials are present."""
    return bool(Config.CONDUCTOR_URL and Config.CONDUCTOR_API_KEY)


# ── real client ───────────────────────────────────────────────────────────────

class ConductorClient:
    """Thin HTTP wrapper around the Conductor API."""

    def __init__(self, url: str, api_key: str) -> None:
        self.base_url = url.rstrip('/')
        self._headers = {
            'X-Authorization': api_key,
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Issue a GET and return parsed JSON."""
        resp = requests.get(
            f'{self.base_url}{path}',
            headers=self._headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: Optional[Dict] = None) -> Any:
        """Issue a POST and return parsed JSON."""
        resp = requests.post(
            f'{self.base_url}{path}',
            headers=self._headers,
            json=json or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_batch_status(self, workflow_name: str, start_time_ms: Optional[int] = None) -> Dict:
        """Return aggregate counts: completed, failed, running, timed_out."""
        params: Dict[str, Any] = {'workflowType': workflow_name, 'size': 1}
        if start_time_ms:
            params['startTime'] = start_time_ms
        # TODO(conductor): confirm the search endpoint path and param names
        data = self._get('/api/workflow/search', params={**params, 'freeText': '*'})
        counts: Dict[str, int] = {'completed': 0, 'failed': 0, 'running': 0, 'timed_out': 0, 'queued': 0}
        for wf in data.get('results', []):
            s = wf.get('status', '')
            if s == 'COMPLETED':
                counts['completed'] += 1
            elif s == 'FAILED':
                counts['failed'] += 1
            elif s in ('RUNNING',):
                counts['running'] += 1
            elif s == 'TIMED_OUT':
                counts['timed_out'] += 1
            elif s in ('SCHEDULED', 'PAUSED'):
                counts['queued'] += 1
        counts['total'] = sum(counts.values())
        return counts

    def search_workflows(self, workflow_name: str, status: str,
                         start_time_ms: Optional[int] = None, size: int = 200) -> List[Dict]:
        """Return list of workflow dicts matching name + status."""
        params: Dict[str, Any] = {
            # TODO(conductor): confirm query syntax for Conductor search API
            'query': f'workflowType="{workflow_name}" AND status="{status}"',
            'size': size,
        }
        if start_time_ms:
            params['startTimeFrom'] = start_time_ms
        data = self._get('/api/workflow/search', params=params)
        return data.get('results', [])

    def get_workflow_detail(self, workflow_id: str) -> Dict:
        """Return full execution detail for one workflow."""
        # TODO(conductor): confirm the workflow detail endpoint path
        return self._get(f'/api/workflow/{workflow_id}')

    def retry_workflow(self, workflow_id: str) -> Dict:
        """Retry a failed workflow by ID."""
        # TODO(conductor): confirm the retry endpoint — may need POST /api/workflow/{id}/retry
        resp = requests.post(
            f'{self.base_url}/api/workflow/{workflow_id}/retry',
            headers=self._headers,
            timeout=30,
        )
        return {'workflow_id': workflow_id, 'status_code': resp.status_code}


# ── mock client ───────────────────────────────────────────────────────────────

# Realistic SIS IDs for mock failures (44 DUPLICATE + 31 FIELD_INTEGRITY + 16 TIMEOUT = 91)
_DUPLICATE_SIS_IDS = [
    'STU00142', 'STU00891', 'STU01203', 'STU01457', 'STU01832', 'STU02091',
    'STU02345', 'STU02678', 'STU02901', 'STU03124', 'STU03456', 'STU03789',
    'STU04012', 'STU04345', 'STU04678', 'STU04901', 'STU05234', 'STU05567',
    'STU05890', 'STU06123', 'STU06456', 'STU06789', 'STU07012', 'STU07345',
    'STU07678', 'STU07901', 'STU08234', 'STU08567', 'STU08890', 'STU09123',
    'STU09456', 'STU09789', 'STU10012', 'STU10345', 'STU10678', 'STU10901',
    'STU11234', 'STU11567', 'STU11890', 'STU12123', 'STU12456', 'STU12789',
    'STU13012', 'STU13345',
]
_FIELD_INTEGRITY_SIS_IDS = [
    'STU13678', 'STU13901', 'STU14234', 'STU14567', 'STU14890', 'STU15123',
    'STU15456', 'STU15789', 'STU16012', 'STU16345', 'STU16678', 'STU16901',
    'STU17234', 'STU17567', 'STU17890', 'STU18123', 'STU18456', 'STU18789',
    'STU19012', 'STU19345', 'STU19678', 'STU19901', 'STU20234', 'STU20567',
    'STU20890', 'STU21123', 'STU21456', 'STU21789', 'STU22012', 'STU22345',
    'STU22678',
]
_TIMEOUT_SIS_IDS = [
    'STU22901', 'STU23234', 'STU23567', 'STU23890', 'STU24123', 'STU24456',
    'STU24789', 'STU25012', 'STU25345', 'STU25678', 'STU25901', 'STU26234',
    'STU26567', 'STU26890', 'STU27123', 'STU27456',
]


def _make_mock_workflow(idx: int, status: str, sis_id: str, error_code: str = '') -> Dict:
    """Build a single mock workflow dict."""
    wf: Dict[str, Any] = {
        # TODO(conductor): confirm workflow dict field names from real Conductor response
        'workflowId': f'wf-mock-{idx:06d}',
        'workflowType': 'SFMigrationWorkflow',
        'status': status,
        'startTime': 1700000000000 + idx * 1000,
        'endTime': 1700000000000 + idx * 1000 + 5000,
        'input': f'{{"sisId": "{sis_id}"}}',
        'reasonForIncompletion': '',
    }
    if error_code:
        wf['reasonForIncompletion'] = (
            f'com.netflix.conductor.common.run.Workflow: {error_code}: '
            f'duplicate value found: SIS_ID__c duplicates value on record with id: {sis_id}'
        )
    return wf


_MOCK_WORKFLOWS: List[Dict] = []
_idx = 1
for _sid in _DUPLICATE_SIS_IDS:
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'FAILED', _sid, 'DUPLICATE_VALUE'))
    _idx += 1
for _sid in _FIELD_INTEGRITY_SIS_IDS:
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'FAILED', _sid, 'FIELD_INTEGRITY_EXCEPTION'))
    _idx += 1
for _sid in _TIMEOUT_SIS_IDS:
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'FAILED', _sid, 'TIMEOUT'))
    _idx += 1
for i in range(212):
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'RUNNING', f'STU{(_idx + 30000):05d}'))
    _idx += 1
for i in range(1253):
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'SCHEDULED', f'STU{(_idx + 30000):05d}'))
    _idx += 1
for i in range(2756):
    _MOCK_WORKFLOWS.append(_make_mock_workflow(_idx, 'COMPLETED', f'STU{(_idx + 30000):05d}'))
    _idx += 1


class MockConductorClient:
    """Returns mock data matching the handoff doc example numbers."""

    def get_batch_status(self, workflow_name: str, start_time_ms: Optional[int] = None) -> Dict:
        """Return mock aggregate counts: 4,312 total, 2,756 completed, 91 failed, etc."""
        return {
            'total': 4312,
            'completed': 2756,
            'failed': 91,
            'running': 212,
            'queued': 1253,
            'timed_out': 16,
        }

    def search_workflows(self, workflow_name: str, status: str,
                         start_time_ms: Optional[int] = None, size: int = 200) -> List[Dict]:
        """Return mock workflows filtered by status."""
        matched = [w for w in _MOCK_WORKFLOWS if w['status'] == status.upper()]
        return matched[:size]

    def get_workflow_detail(self, workflow_id: str) -> Dict:
        """Return mock workflow detail for the given ID."""
        for wf in _MOCK_WORKFLOWS:
            if wf['workflowId'] == workflow_id:
                return {**wf, 'tasks': [], 'variables': {}}
        return {
            'workflowId': workflow_id,
            'workflowType': 'SFMigrationWorkflow',
            'status': 'FAILED',
            'input': '{"sisId": "STU99999"}',
            'reasonForIncompletion': 'DUPLICATE_VALUE: record not found',
            'tasks': [],
        }

    def retry_workflow(self, workflow_id: str) -> Dict:
        """Return mock retry result."""
        return {'workflow_id': workflow_id, 'status_code': 200}


# ── public factory ─────────────────────────────────────────────────────────────

def get_conductor_client():
    """Return a ConductorClient (real or mock) based on config."""
    if Config.CONDUCTOR_MOCK or not _configured():
        logger.info("CONDUCTOR_MOCK active — using MockConductorClient")
        return MockConductorClient()
    logger.info("Connecting to real Conductor at %s", Config.CONDUCTOR_URL)
    return ConductorClient(Config.CONDUCTOR_URL, Config.CONDUCTOR_API_KEY)
