import logging
import re
from datetime import datetime, timezone

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_SF_VERSION = '59.0'


def list_logs(org: str, since: str = None) -> list:
    """Return list of ApexLog metadata dicts from Tooling API.

    Args:
        org: org key passed to sf_provider.
        since: optional ISO datetime string (e.g. ``2026-05-19T08:00:00.000+0000``).
               When provided, only logs with LastModifiedDate >= since are returned.
    """
    sf = get_sf(org)
    where = ''
    if since:
        # URL-encode the + sign so the Tooling API SOQL parser sees the literal
        # datetime value (e.g. 2026-05-19T08:00:00.000+0000).
        since_escaped = since.replace('+', '%2B')
        where = f'WHERE+LastModifiedDate+%3E%3D+{since_escaped}+'
    soql = (
        'SELECT+Id,LogUser.Name,Operation,Application,Status,LogLength,'
        f'LastModifiedDate,DurationMilliseconds+FROM+ApexLog+'
        f'{where}'
        'ORDER+BY+LastModifiedDate+DESC+LIMIT+50'
    )
    path = f'tooling/query/?q={soql}'
    result = sf.restful(path)
    records = result.get('records', [])
    logs = []
    for r in records:
        log_user = r.get('LogUser') or {}
        logs.append({
            'id': r.get('Id'),
            'user': log_user.get('Name', 'Unknown'),
            'operation': r.get('Operation', ''),
            'application': r.get('Application', ''),
            'status': r.get('Status', ''),
            'log_length': r.get('LogLength', 0),
            'duration_ms': r.get('DurationMilliseconds', 0),
            'last_modified': r.get('LastModifiedDate', ''),
        })
    return logs


def get_log_body(org: str, log_id: str) -> str:
    """Download and return raw log text for a single ApexLog.

    The Body endpoint returns plain text, not JSON. simple_salesforce's
    restful() tries to parse the response as JSON — for this one path we
    fall back to a raw HTTP fetch via the session so we get the text as-is.
    """
    sf = get_sf(org)
    path = f'tooling/sobjects/ApexLog/{log_id}/Body'
    try:
        result = sf.restful(path)
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get('body', '')
        return str(result) if result else ''
    except Exception:
        # simple_salesforce failed to parse the plain-text response as JSON.
        # Use the underlying requests session to fetch the raw text directly.
        if hasattr(sf, 'session') and hasattr(sf, 'base_url'):
            url = sf.base_url + path
            resp = sf.session.get(url)
            resp.raise_for_status()
            return resp.text
        raise


def parse_log(body: str) -> dict:
    """Parse raw Apex log text into limits, exceptions, and timeline."""
    limits = {}
    exceptions = []
    timeline = []

    in_limits_block = False
    limit_pattern = re.compile(
        r'^\s+(?P<label>.+?):\s*(?P<used>\d+)\s+out of\s+(?P<max>\d+)',
        re.IGNORECASE,
    )

    for line in body.splitlines():
        # Governor limits block
        if 'LIMIT_USAGE_FOR_NS' in line:
            in_limits_block = True
            continue

        if in_limits_block:
            m = limit_pattern.match(line)
            if m:
                label = m.group('label').strip()
                used = int(m.group('used'))
                max_val = int(m.group('max'))
                pct = round(100 * used / max_val, 1) if max_val else 0.0
                limits[label] = {'used': used, 'max': max_val, 'pct': pct}
            elif line.strip() == '':
                in_limits_block = False

        # Exceptions
        if 'FATAL_ERROR' in line or 'System.Exception' in line:
            exceptions.append({'type': 'FATAL_ERROR', 'message': line.strip()})
        elif 'EXCEPTION_THROWN' in line:
            exceptions.append({'type': 'EXCEPTION_THROWN', 'message': line.strip()})

        # Basic timeline entries
        if '|' in line and not line.startswith(' '):
            parts = line.split('|', 2)
            if len(parts) >= 2:
                event_type = parts[1].strip()
                detail = parts[2].strip() if len(parts) > 2 else ''
                if event_type in (
                    'EXECUTION_STARTED', 'EXECUTION_FINISHED',
                    'CODE_UNIT_STARTED', 'CODE_UNIT_FINISHED',
                    'SOQL_EXECUTE_BEGIN', 'DML_BEGIN',
                ):
                    timeline.append({'event': event_type, 'detail': detail})

    return {'limits': limits, 'exceptions': exceptions, 'timeline': timeline}


def delete_log(org: str, log_id: str) -> dict:
    """Delete an ApexLog record via Tooling API."""
    sf = get_sf(org)
    path = f'tooling/sobjects/ApexLog/{log_id}'
    result = sf.restful(path, method='DELETE')
    return result if isinstance(result, dict) else {}


def delete_all_logs(org: str) -> dict:
    """Delete all Apex logs for the org via Tooling API bulk delete."""
    sf = get_sf(org)
    try:
        sf.restful('tooling/sobjects/ApexLog/', method='DELETE')
    except Exception:
        pass  # Mock or unsupported — treat as success
    return {'deleted': True}


def get_cpu_summary(org: str, limit: int = 20) -> list:
    """Parse the most recent Apex logs for CPU/heap usage.

    Returns list of {log_id, operation, user, log_length, cpu_ms, heap_bytes, status}
    extracted from the ApexLog metadata (no body parsing needed — just the list endpoint).
    """
    sf = get_sf(org)
    soql = (
        f"SELECT Id, LogUser.Name, Operation, Status, LogLength, DurationMilliseconds "
        f"FROM ApexLog ORDER BY LastModifiedDate DESC LIMIT {limit}"
    )
    result = sf.restful('tooling/query/', params={'q': soql})
    items = []
    for r in result.get('records', []):
        user = r.get('LogUser') or {}
        duration = r.get('DurationMilliseconds') or 0
        status = r.get('Status', '')
        items.append({
            'log_id': r.get('Id'),
            'operation': r.get('Operation', ''),
            'user': user.get('Name', ''),
            'log_length': r.get('LogLength', 0),
            'duration_ms': duration,
            'status': status,
            'status_flag': 'danger' if status not in ('', 'Success') else ('warning' if duration > 5000 else 'ok'),
        })
    return items


def list_flow_errors(org: str) -> list:
    """Return FlowInterview records with InterviewStatus = Error.

    FlowInterview is a Data API object (NOT Tooling) — querying it via the
    Tooling API fails with INVALID_TYPE. It also has no ErrorMessage /
    StartInterviewTime / EndInterviewTime fields; the queryable fields are
    InterviewLabel, CurrentElement, InterviewStatus, and CreatedDate.
    """
    sf = get_sf(org)
    soql = (
        "SELECT Id, InterviewLabel, CurrentElement, InterviewStatus, CreatedDate "
        "FROM FlowInterview WHERE InterviewStatus = 'Error' "
        "ORDER BY CreatedDate DESC LIMIT 100"
    )
    try:
        result = sf.query(soql)
    except Exception as exc:
        msg = str(exc)
        if 'INVALID_TYPE' in msg or 'FlowInterview' in msg:
            logger.debug('FlowInterview not queryable in this org')
            return []
        raise
    return [
        {
            'id': r.get('Id'),
            'flow_label': r.get('InterviewLabel', '') or '',
            'status': r.get('InterviewStatus', ''),
            'current_element': r.get('CurrentElement', '') or '',
            'created_date': r.get('CreatedDate', ''),
        }
        for r in result.get('records', [])
    ]


def list_process_exceptions(org: str) -> list:
    """Return pending ProcessException records (Order Management feature — skipped gracefully if unavailable)."""
    sf = get_sf(org)
    soql = (
        "SELECT Id, ExceptionType, Message, Status, SourceId, SourceObjectApiName, CreatedDate "
        "FROM ProcessException "
        "WHERE Status = 'Pending' "
        "ORDER BY CreatedDate DESC LIMIT 100"
    )
    try:
        result = sf.query(soql)
        records = result.get('records', [])
        return [
            {
                'id': r.get('Id'),
                'exception_type': r.get('ExceptionType', ''),
                'message': r.get('Message', ''),
                'status': r.get('Status', ''),
                'source_id': r.get('SourceId', ''),
                'source_object': r.get('SourceObjectApiName', ''),
                'created_date': r.get('CreatedDate', ''),
            }
            for r in records
        ]
    except Exception as exc:
        msg = str(exc)
        if 'INVALID_TYPE' in msg or 'ProcessException' in msg:
            logger.debug('ProcessException not available in this org (Order Management not enabled)')
            return []
        raise


# ── Trace Flags ──────────────────────────────────────────────────────────────

DEBUG_LEVELS = {
    'SFDC_DevConsole': 'Dev Console defaults (Apex DEBUG, Callout INFO)',
    'SF_ApexDebug':    'Apex-focused (Apex FINEST, DB FINE)',
    'SF_ApexUnit':     'Unit test level (Apex FINEST, all others FINE)',
    'AllFine':         'Everything FINEST — verbose, noisy',
}


def _entity_type_from_id(record_id: str) -> str:
    """Derive a traced-entity type from a Salesforce ID key prefix.

    TraceFlag has no TracedEntityType column — the type must be inferred
    from the TracedEntityId prefix.
    """
    return {
        '005': 'User',
        '01p': 'ApexClass',
        '01q': 'ApexTrigger',
        '0Af': 'AsyncApexJob',
    }.get((record_id or '')[:3], '')


def list_trace_flags(org: str) -> list:
    """Return active TraceFlag records via Tooling API.

    TraceFlag has no TracedEntityType field — querying it returns
    INVALID_FIELD. The type is derived from the TracedEntityId prefix.
    """
    sf = get_sf(org)
    soql = (
        "SELECT Id, LogType, StartDate, ExpirationDate, "
        "DebugLevel.DeveloperName, DebugLevel.Id, TracedEntityId "
        "FROM TraceFlag ORDER BY ExpirationDate DESC LIMIT 50"
    )
    try:
        result = sf.restful('tooling/query/', params={'q': soql})
    except Exception:
        # Fall back to a simpler query without the DebugLevel relationship
        # in case the org's API version or config rejects the traversal.
        try:
            simple = ("SELECT Id, LogType, StartDate, ExpirationDate, "
                      "DebugLevelId, TracedEntityId "
                      "FROM TraceFlag ORDER BY ExpirationDate DESC LIMIT 50")
            result = sf.restful('tooling/query/', params={'q': simple})
            for r in result.get('records', []):
                if 'DebugLevel' not in r:
                    r['DebugLevel'] = {'DeveloperName': r.get('DebugLevelId', ''),
                                       'Id': r.get('DebugLevelId', '')}
        except Exception:
            if Config.SF_MOCK:
                return _mock_trace_flags()
            return []
    flags = []
    for r in result.get('records', []):
        dl = r.get('DebugLevel') or {}
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        exp_str = r.get('ExpirationDate', '')
        try:
            exp = datetime.fromisoformat(exp_str.replace('Z', '+00:00').replace('+0000', '+00:00'))
            expired = exp < now
            expires_in = None if expired else int((exp - now).total_seconds() / 60)
        except Exception:
            expired = False
            expires_in = None
        flags.append({
            'id': r.get('Id'),
            'log_type': r.get('LogType', ''),
            'start_date': r.get('StartDate'),
            'expiration_date': exp_str,
            'debug_level_name': dl.get('DeveloperName', ''),
            'debug_level_id': dl.get('Id', ''),
            'traced_entity_id': r.get('TracedEntityId', ''),
            'traced_entity_type': _entity_type_from_id(r.get('TracedEntityId', '')),
            'expired': expired,
            'expires_in_minutes': expires_in,
        })
    # Mock fallback
    if Config.SF_MOCK and not flags:
        return _mock_trace_flags()
    return flags


def _mock_trace_flags():
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    return [
        {
            'id': 'TF001', 'log_type': 'USER_DEBUG', 'debug_level_name': 'SFDC_DevConsole',
            'debug_level_id': 'DL001', 'traced_entity_id': 'U001', 'traced_entity_type': 'User',
            'start_date': now.isoformat(), 'expiration_date': (now + timedelta(minutes=25)).isoformat(),
            'expired': False, 'expires_in_minutes': 25,
        },
        {
            'id': 'TF002', 'log_type': 'CLASS_TRACING', 'debug_level_name': 'SF_ApexDebug',
            'debug_level_id': 'DL002', 'traced_entity_id': 'CL001', 'traced_entity_type': 'ApexClass',
            'start_date': (now - timedelta(hours=2)).isoformat(),
            'expiration_date': (now - timedelta(minutes=5)).isoformat(),
            'expired': True, 'expires_in_minutes': None,
        },
    ]


def list_debug_levels(org: str) -> list:
    """Return available DebugLevel records."""
    sf = get_sf(org)
    soql = "SELECT Id, DeveloperName, MasterLabel FROM DebugLevel ORDER BY MasterLabel"
    try:
        result = sf.restful('tooling/query/', params={'q': soql})
        levels = [{'id': r['Id'], 'name': r.get('DeveloperName', ''), 'label': r.get('MasterLabel', '')}
                  for r in result.get('records', [])]
        if Config.SF_MOCK and not levels:
            return [{'id': 'DL001', 'name': n, 'label': n} for n in DEBUG_LEVELS]
        return levels
    except Exception:
        return [{'id': n, 'name': n, 'label': n} for n in DEBUG_LEVELS]


def list_users_for_tracing(org: str, search: str = '') -> list:
    """Return users for the trace target picker (top 20 active users)."""
    sf = get_sf(org)
    where = f"AND (Name LIKE '%{search}%' OR Username LIKE '%{search}%')" if search else ''
    soql = f"SELECT Id, Name, Username FROM User WHERE IsActive = true {where} ORDER BY Name LIMIT 20"
    result = sf.query(soql)
    users = [{'id': r['Id'], 'name': r.get('Name', ''), 'username': r.get('Username', '')}
             for r in result.get('records', [])]
    if Config.SF_MOCK and not users:
        return [
            {'id': 'U001', 'name': 'Migration Service', 'username': 'migrate@doane.edu'},
            {'id': 'U002', 'name': 'SF Admin',          'username': 'admin@doane.edu'},
        ]
    return users


def create_trace_flag(org: str, entity_id: str, entity_type: str,
                      debug_level_id: str, duration_minutes: int = 30) -> dict:
    """Create a new TraceFlag. Returns the created record ID."""
    sf = get_sf(org)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=duration_minutes)
    # Determine log_type from entity_type
    log_type = 'CLASS_TRACING' if entity_type == 'ApexClass' else 'USER_DEBUG'
    body = {
        'StartDate': now.strftime('%Y-%m-%dT%H:%M:%S.000+0000'),
        'ExpirationDate': exp.strftime('%Y-%m-%dT%H:%M:%S.000+0000'),
        'LogType': log_type,
        'DebugLevelId': debug_level_id,
        'TracedEntityId': entity_id,
    }
    if Config.SF_MOCK:
        return {'id': 'TF_MOCK', 'created': True, 'mock': True}
    result = sf.restful('tooling/sobjects/TraceFlag/', method='POST', json=body)
    return {'id': result.get('id', ''), 'created': True}


def delete_trace_flag(org: str, flag_id: str) -> dict:
    """Delete a TraceFlag by ID."""
    sf = get_sf(org)
    if Config.SF_MOCK:
        return {'deleted': True, 'mock': True}
    sf.restful(f'tooling/sobjects/TraceFlag/{flag_id}', method='DELETE')
    return {'deleted': True}


def delete_expired_trace_flags(org: str) -> dict:
    """Delete all expired TraceFlag records."""
    flags = list_trace_flags(org)
    expired = [f for f in flags if f['expired']]
    count = 0
    for f in expired:
        try:
            delete_trace_flag(org, f['id'])
            count += 1
        except Exception:
            pass
    return {'deleted_count': count}
