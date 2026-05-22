"""Conductor provider — returns a live ConductorClient.

There is no mock mode. Conductor credentials (CONDUCTOR_URL + CONDUCTOR_API_KEY)
must be configured; an unconfigured environment raises a clear error rather than
silently falling back to fabricated workflow data.
"""
import logging
from typing import Any, Dict, List, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


# ── env gate ──────────────────────────────────────────────────────────────────

def _configured() -> bool:
    """Return True when real Conductor credentials are present."""
    return bool(Config.CONDUCTOR_URL and Config.CONDUCTOR_API_KEY)


# ── client ────────────────────────────────────────────────────────────────────

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


# ── public factory ─────────────────────────────────────────────────────────────

def get_conductor_client() -> ConductorClient:
    """Return a live ConductorClient.

    Raises RuntimeError when Conductor credentials are not configured — the app
    never substitutes fabricated data for a missing connection.
    """
    if not _configured():
        raise RuntimeError(
            "Conductor is not configured. Set CONDUCTOR_URL and "
            "CONDUCTOR_API_KEY in the environment."
        )
    logger.info("Connecting to Conductor at %s", Config.CONDUCTOR_URL)
    return ConductorClient(Config.CONDUCTOR_URL, Config.CONDUCTOR_API_KEY)
