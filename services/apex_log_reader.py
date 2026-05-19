import logging
import re

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_SF_VERSION = '59.0'


def list_logs(org: str) -> list:
    """Return list of ApexLog metadata dicts from Tooling API."""
    sf = get_sf(org)
    soql = (
        'SELECT+Id,LogUser.Name,Operation,Application,Status,LogLength,'
        'LastModifiedDate,DurationMilliseconds+FROM+ApexLog+'
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
    """Download and return raw log text for a single ApexLog."""
    sf = get_sf(org)
    path = f'tooling/sobjects/ApexLog/{log_id}/Body'
    result = sf.restful(path)
    if isinstance(result, str):
        return result
    return result.get('body', '') if isinstance(result, dict) else ''


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


def list_flow_errors(org: str) -> list:
    """Return FlowInterview records with InterviewStatus = Error."""
    sf = get_sf(org)
    soql = (
        'SELECT+Id,FlowVersionId,InterviewStatus,CurrentElement,ErrorMessage,'
        'StartInterviewTime,EndInterviewTime+FROM+FlowInterview+'
        'WHERE+InterviewStatus+=+%27Error%27+'
        'ORDER+BY+StartInterviewTime+DESC+LIMIT+100'
    )
    path = f'tooling/query/?q={soql}'
    result = sf.restful(path)
    records = result.get('records', [])
    return [
        {
            'id': r.get('Id'),
            'flow_version_id': r.get('FlowVersionId', ''),
            'status': r.get('InterviewStatus', ''),
            'current_element': r.get('CurrentElement', ''),
            'error_message': r.get('ErrorMessage', ''),
            'start_time': r.get('StartInterviewTime', ''),
            'end_time': r.get('EndInterviewTime', ''),
        }
        for r in records
    ]


def list_process_exceptions(org: str) -> list:
    """Return pending ProcessException records."""
    sf = get_sf(org)
    soql = (
        'SELECT+Id,ExceptionType,Message,Status,SourceId,SourceObjectApiName,'
        'CreatedDate+FROM+ProcessException+'
        'WHERE+Status+=+%27Pending%27+'
        'ORDER+BY+CreatedDate+DESC+LIMIT+100'
    )
    path = f'tooling/query/?q={soql}'
    result = sf.restful(path)
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
