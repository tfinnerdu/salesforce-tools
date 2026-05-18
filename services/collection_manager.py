import json
import logging
import re
from typing import Optional

import requests

from db import get_cursor

logger = logging.getLogger(__name__)


def substitute_variables(text: str, env_vars: dict) -> str:
    """Replace {{KEY}} placeholders with values from env_vars."""
    def _replace(match):
        key = match.group(1)
        return env_vars.get(key, match.group(0))
    return re.sub(r'\{\{(\w+)\}\}', _replace, text)


def _apply_env(obj, env_vars: dict):
    """Recursively substitute variables in strings within a dict/list."""
    if isinstance(obj, str):
        return substitute_variables(obj, env_vars)
    if isinstance(obj, dict):
        return {k: _apply_env(v, env_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_apply_env(item, env_vars) for item in obj]
    return obj


def _extract_url(url_obj) -> str:
    """Extract a plain URL string from a Postman URL object or raw string."""
    if isinstance(url_obj, str):
        return url_obj
    if isinstance(url_obj, dict):
        raw = url_obj.get('raw', '')
        if raw:
            return raw
        # Reconstruct from parts
        protocol = url_obj.get('protocol', 'https')
        host = '.'.join(url_obj.get('host', []))
        path = '/'.join(url_obj.get('path', []))
        return f"{protocol}://{host}/{path}"
    return ''


def import_collection(content: str) -> dict:
    """Parse Postman v2.1 JSON content, store in DB, return saved record."""
    try:
        data = json.loads(content)
    except Exception as exc:
        logger.error("import_collection: JSON parse error: %s", exc)
        raise ValueError(f"Invalid JSON: {exc}") from exc

    name = data.get('info', {}).get('name', 'Imported Collection')
    return create_collection(name=name, collection_json=data)


def create_collection(name: str, collection_json: dict) -> dict:
    """Insert a new collection into DB and return the saved record."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO api_collections (name, collection_json) "
                "VALUES (%s, %s) "
                "RETURNING id, name, collection_json, created_at, updated_at",
                (name, json.dumps(collection_json)),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
    except Exception as exc:
        logger.error("create_collection failed: %s", exc)
        return {}


def list_collections() -> list:
    """Return all collections ordered by name."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, name, created_at, updated_at FROM api_collections ORDER BY name"
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("list_collections failed: %s", exc)
        return []


def run_collection(col_id: int, env_overrides: dict) -> list:
    """Execute each request in the collection; return result per request."""
    # Fetch collection from DB
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT collection_json FROM api_collections WHERE id = %s",
                (col_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.error("run_collection: DB fetch failed for id=%s: %s", col_id, exc)
        return []

    if not row:
        logger.warning("run_collection: collection %s not found", col_id)
        return []

    col_data = row['collection_json']
    if isinstance(col_data, str):
        try:
            col_data = json.loads(col_data)
        except Exception:
            return []

    items = col_data.get('item', [])
    results = []

    for item in items:
        req_name = item.get('name', 'Unnamed')
        req = item.get('request', {})

        method = req.get('method', 'GET').upper()
        url_raw = _extract_url(req.get('url', ''))
        url = substitute_variables(url_raw, env_overrides)

        # Build headers dict
        headers = {}
        for h in req.get('header', []):
            k = substitute_variables(h.get('key', ''), env_overrides)
            v = substitute_variables(h.get('value', ''), env_overrides)
            if k:
                headers[k] = v

        # Build body
        body_obj = req.get('body', {})
        body_text = None
        if body_obj:
            mode = body_obj.get('mode', '')
            if mode == 'raw':
                body_text = substitute_variables(body_obj.get('raw', ''), env_overrides)
            elif mode == 'urlencoded':
                parts = []
                for param in body_obj.get('urlencoded', []):
                    pk = substitute_variables(param.get('key', ''), env_overrides)
                    pv = substitute_variables(param.get('value', ''), env_overrides)
                    parts.append(f"{pk}={pv}")
                body_text = '&'.join(parts)

        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body_text,
                timeout=30,
            )
            status_code = resp.status_code
            passed = status_code < 400
            preview = resp.text[:500] if resp.text else ''
            error = None
        except Exception as exc:
            status_code = 0
            passed = False
            preview = ''
            error = str(exc)
            logger.error("run_collection: request '%s' failed: %s", req_name, exc)

        results.append({
            'name': req_name,
            'url': url,
            'method': method,
            'status_code': status_code,
            'passed': passed,
            'response_preview': preview,
            'error': error,
        })

    return results


def delete_collection(col_id: int) -> None:
    """Delete a collection by id."""
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM api_collections WHERE id = %s", (col_id,))
    except Exception as exc:
        logger.error("delete_collection failed id=%s: %s", col_id, exc)
