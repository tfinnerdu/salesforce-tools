"""Salesforce provider — returns a live simple_salesforce client.

There is no mock mode. Every org used by the app must have real credentials
configured (SF_<ORG>_USERNAME / SF_<ORG>_PASSWORD). An unconfigured org raises
a clear error rather than silently falling back to fabricated data.
"""
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Generator

from config import Config, get_org_config

logger = logging.getLogger(__name__)

# ── DML helpers ───────────────────────────────────────────────────────────────

_dml_lock = threading.Lock()
_last_dml_time: float = 0.0


def dml_throttle() -> None:
    """Sleep if needed to honour SF_DML_RATE_LIMIT (calls/sec). No-op when 0."""
    rate = Config.SF_DML_RATE_LIMIT
    if not rate:
        return
    global _last_dml_time
    with _dml_lock:
        elapsed = time.monotonic() - _last_dml_time
        min_gap = 1.0 / rate
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        _last_dml_time = time.monotonic()


def set_bypass_triggers(sf, enable: bool) -> None:
    """Flip the org-level bypass-triggers Custom Setting via REST. No-op when unconfigured."""
    setting = Config.SF_BYPASS_SETTING
    field = Config.SF_BYPASS_FIELD
    if not setting or not field:
        return
    try:
        sf.restful(f'sobjects/{setting}/', method='PATCH', json={field: enable})
        logger.info("bypass_triggers set to %s on %s", enable, setting)
    except Exception as exc:
        logger.warning("set_bypass_triggers(%s) failed: %s", enable, exc)


@contextmanager
def dml_guard(sf, bypass: bool = False) -> Generator:
    """Rate-throttle and optionally bypass Apex triggers around a DML block."""
    dml_throttle()
    if bypass:
        set_bypass_triggers(sf, True)
    try:
        yield
    finally:
        if bypass:
            set_bypass_triggers(sf, False)


# ── Bulk API 2.0 helpers ──────────────────────────────────────────────────────

def bulk2_dml(sf, object_name: str, operation: str, records: list,
              external_id_field: str = '') -> dict:
    """Run a Bulk API 2.0 (``sf.bulk2``) DML operation on a list of record dicts.

    Returns ``{total, succeeded, failed, job_ids}``.

    Note: simple_salesforce 1.12.5's bulk2 ``delete`` cannot accept ``records=``
    (its delete branch unconditionally opens ``csv_file``) — delete IDs are
    written to a temporary single-column CSV and passed as ``csv_file=``.
    """
    bulk_obj = getattr(sf.bulk2, object_name)
    op = (operation or '').lower()

    if op == 'delete':
        import csv as _csv
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.csv')
        try:
            with os.fdopen(fd, 'w', newline='', encoding='utf-8') as fh:
                writer = _csv.writer(fh)
                writer.writerow(['Id'])
                for r in records:
                    writer.writerow([r.get('Id', '')])
            job_results = bulk_obj.delete(csv_file=path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    elif op == 'insert':
        job_results = bulk_obj.insert(records=records)
    elif op == 'update':
        job_results = bulk_obj.update(records=records)
    elif op == 'upsert':
        if not external_id_field:
            raise ValueError('external_id_field is required for upsert')
        job_results = bulk_obj.upsert(records=records, external_id_field=external_id_field)
    else:
        raise ValueError(f"Unknown bulk operation '{operation}'")

    job_results = job_results or []
    total     = sum(int(j.get('numberRecordsTotal', 0) or 0) for j in job_results)
    processed = sum(int(j.get('numberRecordsProcessed', 0) or 0) for j in job_results)
    failed    = sum(int(j.get('numberRecordsFailed', 0) or 0) for j in job_results)
    return {
        'total': total or processed,
        'succeeded': max(processed - failed, 0),
        'failed': failed,
        'job_ids': [j.get('job_id') for j in job_results if j.get('job_id')],
    }


def bulk2_failed_records(sf, object_name: str, job_ids: list) -> str:
    """Return the combined failed-record CSV across Bulk API 2.0 ingest jobs.

    The CSV columns are ``sf__Id``, ``sf__Error``, and the original request
    fields. Best-effort — returns '' if the detail cannot be fetched.
    """
    bulk_obj = getattr(sf.bulk2, object_name)
    parts = []
    for jid in job_ids:
        try:
            text = bulk_obj.get_failed_records(jid)
            if text and text.strip():
                parts.append(text.strip())
        except Exception as exc:
            logger.warning('bulk2 get_failed_records failed for %s: %s', jid, exc)
    if not parts:
        return ''
    combined = [parts[0]]
    for p in parts[1:]:
        combined.extend(p.splitlines()[1:])  # drop repeated header
    return '\n'.join(combined)


# ── helpers ──────────────────────────────────────────────────────────────────

def _configured(org: str) -> bool:
    """Return True when real SF credentials are present for this org."""
    cfg = get_org_config(org)
    return bool(cfg['username'] and cfg['password'])


def assert_orgs_comparable(left_org: str, right_org: str) -> None:
    """Raise ValueError when a diff names an org with no credentials configured.

    A diff is only meaningful when both orgs can actually be connected to.
    Surface a missing-credentials org as a clear configuration error instead
    of letting the connection fail mid-diff.
    """
    for org in (left_org, right_org):
        if not _configured(org):
            raise ValueError(
                f"Org '{org}' has no Salesforce credentials configured "
                f"(SF_{org.upper()}_USERNAME / SF_{org.upper()}_PASSWORD). "
                f"Configure the org, or pick one that is."
            )


def available_orgs() -> list:
    """Org names to offer in diff pickers — only orgs with credentials configured."""
    candidates = ['dev', 'prod', 'sandbox']
    return [o for o in candidates if _configured(o)]


# ── public factory ─────────────────────────────────────────────────────────────

def get_sf(org: str = 'dev'):
    """Return a live Salesforce client for the given org.

    Raises RuntimeError when the org has no credentials configured — the app
    never substitutes fabricated data for a missing connection.
    """
    if not _configured(org):
        raise RuntimeError(
            f"Org '{org}' has no Salesforce credentials configured. "
            f"Set SF_{org.upper()}_USERNAME and SF_{org.upper()}_PASSWORD "
            f"(and SF_{org.upper()}_TOKEN if required) in the environment."
        )

    from simple_salesforce import Salesforce  # type: ignore
    cfg = get_org_config(org)
    api_version = cfg['api_version']
    # SOAP login endpoint rejects versions above ~59; authenticate with capped version
    # then upgrade base_url so all REST calls use the configured API version.
    soap_version = Config.SF_SOAP_AUTH_VERSION
    logger.info("Connecting to Salesforce org '%s' as %s (auth v%s → API v%s)",
                org, cfg['username'], soap_version, api_version)
    sf = Salesforce(
        username=cfg['username'],
        password=cfg['password'],
        security_token=cfg['security_token'],
        domain=cfg['domain'],
        version=soap_version,
    )
    if api_version != soap_version:
        sf.sf_version = api_version
        sf.base_url = f"https://{sf.sf_instance}/services/data/v{api_version}/"
    return sf
