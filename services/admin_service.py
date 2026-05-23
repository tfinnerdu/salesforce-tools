import logging
from datetime import datetime, timedelta, timezone

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_JOB_TYPE_LABELS = {
    '0': 'Unknown',
    '3': 'Data Export',
    '7': 'Scheduled Apex',
}

_STATE_LABELS = {
    'WAITING': 'Waiting',
    'ACQUIRED': 'Acquired',
    'EXECUTING': 'Executing',
    'COMPLETE': 'Complete',
    'DELETED': 'Deleted',
    'PAUSED': 'Paused',
    'ERROR': 'Error',
    'BLOCKED': 'Blocked',
}


def get_scheduled_jobs(org: str) -> list:
    sf = get_sf(org)
    soql = (
        "SELECT Id, CronJobDetail.Name, CronJobDetail.JobType, State, NextFireTime, "
        "PreviousFireTime, StartTime, TimesTriggered, CronExpression "
        "FROM CronTrigger ORDER BY NextFireTime ASC LIMIT 200"
    )
    result = sf.query(soql)
    jobs = []
    for r in result.get('records', []):
        detail = r.get('CronJobDetail') or {}
        job_type_code = str(detail.get('JobType', ''))
        state = r.get('State', '')
        jobs.append({
            'id': r.get('Id'),
            'name': detail.get('Name', ''),
            'job_type_code': job_type_code,
            'job_type_label': _JOB_TYPE_LABELS.get(job_type_code, f'Type {job_type_code}'),
            'state': state,
            'state_label': _STATE_LABELS.get(state, state),
            'next_fire_time': r.get('NextFireTime'),
            'previous_fire_time': r.get('PreviousFireTime'),
            'start_time': r.get('StartTime'),
            'times_triggered': r.get('TimesTriggered', 0),
            'cron_expression': r.get('CronExpression', ''),
        })
    return jobs


def get_test_coverage(org: str) -> dict:
    sf = get_sf(org)
    soql = (
        "SELECT ApexClassOrTrigger.Name, ApexClassOrTriggerId, "
        "NumLinesCovered, NumLinesUncovered "
        "FROM ApexCodeCoverageAggregate "
        "ORDER BY NumLinesUncovered DESC LIMIT 200"
    )
    result = sf.restful('tooling/query/', params={'q': soql})
    classes = []
    passing = 0
    failing = 0
    below_threshold = 0
    for r in result.get('records', []):
        detail = r.get('ApexClassOrTrigger') or {}
        covered = r.get('NumLinesCovered', 0) or 0
        uncovered = r.get('NumLinesUncovered', 0) or 0
        total = covered + uncovered
        pct = round(covered / total * 100, 1) if total else 0.0
        if pct >= 75:
            status = 'green'
            passing += 1
        elif pct >= 50:
            status = 'amber'
            below_threshold += 1
        else:
            status = 'red'
            failing += 1
            below_threshold += 1
        classes.append({
            'id': r.get('ApexClassOrTriggerId'),
            'name': detail.get('Name', ''),
            'num_lines_covered': covered,
            'num_lines_uncovered': uncovered,
            'total_lines': total,
            'pct': pct,
            'status': status,
        })
    summary = {
        'total': len(classes),
        'passing': passing,
        'failing': failing,
        'below_threshold': below_threshold,
    }
    return {'classes': classes, 'summary': summary}


def get_deploy_history(org: str) -> list:
    sf = get_sf(org)
    soql = (
        "SELECT Id, Status, StartDate, CompletedDate, CreatedBy.Name, "
        "NumberComponentsTotal, NumberComponentErrors, "
        "NumberTestsCompleted, NumberTestErrors, StateDetail "
        "FROM DeployRequest ORDER BY StartDate DESC LIMIT 50"
    )
    result = sf.restful('tooling/query/', params={'q': soql})
    deploys = []
    for r in result.get('records', []):
        start = r.get('StartDate')
        completed = r.get('CompletedDate')
        duration_seconds = None
        if start and completed:
            try:
                fmt = '%Y-%m-%dT%H:%M:%S.%f%z'
                t_start = datetime.strptime(start.replace('+0000', '+00:00'), '%Y-%m-%dT%H:%M:%S.%f%z')
                t_end = datetime.strptime(completed.replace('+0000', '+00:00'), '%Y-%m-%dT%H:%M:%S.%f%z')
                duration_seconds = round((t_end - t_start).total_seconds())
            except Exception:
                pass
        creator = r.get('CreatedBy') or {}
        status = r.get('Status', '')
        deploys.append({
            'id': r.get('Id'),
            'status': status,
            'start_date': start,
            'completed_date': completed,
            'duration_seconds': duration_seconds,
            'created_by': creator.get('Name', ''),
            'num_components_total': r.get('NumberComponentsTotal', 0),
            'num_component_errors': r.get('NumberComponentErrors', 0),
            'num_tests_completed': r.get('NumberTestsCompleted', 0),
            'num_test_errors': r.get('NumberTestErrors', 0),
            'state_detail': r.get('StateDetail'),
        })
    return deploys


def _days_since(ts: str) -> int:
    if not ts:
        return -1
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+0000', '+00:00'))
        now = datetime.now(timezone.utc)
        return (now - dt).days
    except Exception:
        return -1


def get_user_audit(org: str) -> dict:
    sf = get_sf(org)
    soql = (
        "SELECT Id, Name, Username, IsActive, LastLoginDate, UserType, Profile.Name, CreatedDate "
        "FROM User "
        "WHERE UserType IN ('Standard', 'PowerPartner', 'CSPLitePortal', 'PowerCustomerSuccess') "
        "ORDER BY LastLoginDate DESC NULLS LAST LIMIT 500"
    )
    result = sf.query(soql)
    users = []
    total_active = 0
    inactive_90d = 0
    never_logged_in = 0
    sysadmins = 0
    for r in result.get('records', []):
        is_active = r.get('IsActive', False)
        last_login = r.get('LastLoginDate')
        profile = r.get('Profile') or {}
        profile_name = profile.get('Name', '')
        days_since_login = _days_since(last_login) if last_login else None

        flag = None
        if not is_active:
            flag = 'inactive'
        elif last_login is None:
            flag = 'never_logged_in'
            never_logged_in += 1
        elif days_since_login is not None and days_since_login > 90:
            flag = 'inactive_90d'
            inactive_90d += 1

        if is_active:
            total_active += 1
        if is_active and 'system administrator' in profile_name.lower():
            sysadmins += 1

        users.append({
            'id': r.get('Id'),
            'name': r.get('Name', ''),
            'username': r.get('Username', ''),
            'is_active': is_active,
            'last_login_date': last_login,
            'days_since_login': days_since_login,
            'user_type': r.get('UserType', ''),
            'profile_name': profile_name,
            'created_date': r.get('CreatedDate'),
            'flag': flag,
        })
    summary = {
        'total_active': total_active,
        'inactive_90d': inactive_90d,
        'never_logged_in': never_logged_in,
        'sysadmins': sysadmins,
    }
    return {'users': users, 'summary': summary}


# ── Record Types ───────────────────────────────────────────────────────────────

def _mock_record_types():
    return [
        {'id': '012000000000001', 'name': 'Person Account',      'developer_name': 'PersonAccount',      'sobject_type': 'Account',     'is_active': True,  'description': 'Person Account record type', 'record_count': 4312},
        {'id': '012000000000002', 'name': 'Household Account',   'developer_name': 'HouseholdAccount',   'sobject_type': 'Account',     'is_active': True,  'description': 'Household/family account',   'record_count': 87},
        {'id': '012000000000003', 'name': 'Standard Opportunity', 'developer_name': 'Standard',           'sobject_type': 'Opportunity', 'is_active': True,  'description': '',                           'record_count': None},
        {'id': '012000000000004', 'name': 'Standard Case',       'developer_name': 'Standard',           'sobject_type': 'Case',        'is_active': True,  'description': '',                           'record_count': None},
        {'id': '012000000000005', 'name': 'EDC Case',            'developer_name': 'EDC_Case',           'sobject_type': 'Case',        'is_active': True,  'description': 'Education Cloud Case',       'record_count': None},
        {'id': '012000000000006', 'name': 'Standard Campaign',   'developer_name': 'Standard',           'sobject_type': 'Campaign',    'is_active': False, 'description': '',                           'record_count': None},
    ]


def get_record_types(org: str) -> list:
    """Query RecordType with record count per type."""
    if Config.SHOW_MOCK:
        return _mock_record_types()

    sf = get_sf(org)
    rt_soql = (
        "SELECT Id, Name, DeveloperName, SobjectType, IsActive, Description "
        "FROM RecordType ORDER BY SobjectType, Name"
    )
    result = sf.query_all(rt_soql)
    record_types = []
    for r in result.get('records', []):
        record_types.append({
            'id': r.get('Id'),
            'name': r.get('Name', ''),
            'developer_name': r.get('DeveloperName', ''),
            'sobject_type': r.get('SobjectType', ''),
            'is_active': r.get('IsActive', False),
            'description': r.get('Description') or '',
            'record_count': None,  # populated below where feasible
        })

    # Step 2: for common objects, get count by RecordTypeId
    COUNTABLE = {'Account', 'Opportunity', 'Case', 'Campaign', 'Contact'}
    by_obj = {}
    for rt in record_types:
        by_obj.setdefault(rt['sobject_type'], []).append(rt)

    for sobject, rts in by_obj.items():
        if sobject not in COUNTABLE:
            continue
        try:
            count_soql = f"SELECT RecordTypeId, COUNT(Id) cnt FROM {sobject} GROUP BY RecordTypeId"
            count_result = sf.query_all(count_soql)
            counts = {r.get('RecordTypeId'): r.get('cnt', 0) for r in count_result.get('records', [])}
            for rt in rts:
                rt['record_count'] = counts.get(rt['id'], 0)
        except Exception:
            pass  # counts remain None

    return record_types


# ── Email Templates ────────────────────────────────────────────────────────────

def _mock_email_templates():
    return [
        {'id': '00X01', 'name': 'Welcome Email',         'developer_name': 'Welcome_Email',         'folder_name': 'Student Communications', 'subject': 'Welcome to Doane University!',       'encoding': 'UTF-8',       'is_active': True,  'last_modified_date': '2025-08-15T10:00:00.000Z', 'last_modified_by': 'Admin User'},
        {'id': '00X02', 'name': 'Application Received',  'developer_name': 'Application_Received',  'folder_name': 'Student Communications', 'subject': 'We received your application',       'encoding': 'UTF-8',       'is_active': True,  'last_modified_date': '2025-09-01T14:00:00.000Z', 'last_modified_by': 'Admin User'},
        {'id': '00X03', 'name': 'Migration Batch Alert', 'developer_name': 'Migration_Batch_Alert', 'folder_name': 'IT Internal',            'subject': 'Migration batch completed: {batch}', 'encoding': 'UTF-8',       'is_active': True,  'last_modified_date': '2025-10-20T09:00:00.000Z', 'last_modified_by': 'SF Admin'},
        {'id': '00X04', 'name': 'Financial Aid Update',  'developer_name': 'FinAid_Update',         'folder_name': 'Financial Aid',          'subject': 'Update on your financial aid',       'encoding': 'UTF-8',       'is_active': True,  'last_modified_date': '2025-07-01T12:00:00.000Z', 'last_modified_by': 'FinAid Team'},
        {'id': '00X05', 'name': 'Legacy Welcome (OLD)',  'developer_name': 'Legacy_Welcome',        'folder_name': 'Unfiled Public',         'subject': 'Welcome (deprecated)',               'encoding': 'ISO-8859-1',  'is_active': False, 'last_modified_date': '2024-01-10T08:00:00.000Z', 'last_modified_by': 'Admin User'},
    ]


def get_email_templates(org: str) -> list:
    """Query EmailTemplate via standard API."""
    if Config.SHOW_MOCK:
        return _mock_email_templates()

    sf = get_sf(org)
    soql = (
        "SELECT Id, Name, DeveloperName, FolderId, FolderName, Subject, "
        "Encoding, IsActive, LastModifiedDate, LastModifiedBy.Name "
        "FROM EmailTemplate ORDER BY FolderName, Name"
    )
    result = sf.query_all(soql)
    templates = []
    for r in result.get('records', []):
        modifier = r.get('LastModifiedBy') or {}
        templates.append({
            'id': r.get('Id'),
            'name': r.get('Name', ''),
            'developer_name': r.get('DeveloperName', ''),
            'folder_name': r.get('FolderName', ''),
            'subject': r.get('Subject', ''),
            'encoding': r.get('Encoding', ''),
            'is_active': r.get('IsActive', True),
            'last_modified_date': r.get('LastModifiedDate'),
            'last_modified_by': modifier.get('Name', ''),
        })
    return templates


# ── Setup Audit Trail ──────────────────────────────────────────────────────────

def _mock_audit_trail():
    now = datetime.now(timezone.utc)
    return [
        {'id': 'SAT01', 'action': 'Changed',   'section': 'Permission Sets',       'created_date': (now - timedelta(hours=2)).isoformat(),  'created_by': 'SF Admin', 'display': 'Changed permission set Migration Admin: added Create on Account'},
        {'id': 'SAT02', 'action': 'Created',   'section': 'Custom Fields',         'created_date': (now - timedelta(hours=5)).isoformat(),  'created_by': 'SF Admin', 'display': 'Created custom field Account.SIS_ID__c'},
        {'id': 'SAT03', 'action': 'Activated', 'section': 'Flows',                 'created_date': (now - timedelta(days=1)).isoformat(),   'created_by': 'SF Admin', 'display': 'Activated Flow: Student_Update_Handler version 3'},
        {'id': 'SAT04', 'action': 'Changed',   'section': 'Named Credentials',     'created_date': (now - timedelta(days=2)).isoformat(),   'created_by': 'SF Admin', 'display': 'Changed Named Credential: Conductor API endpoint'},
        {'id': 'SAT05', 'action': 'Changed',   'section': 'Remote Site Settings',  'created_date': (now - timedelta(days=3)).isoformat(),   'created_by': 'SF Admin', 'display': 'Changed Remote Site Setting: Ethos — enabled'},
        {'id': 'SAT06', 'action': 'Installed', 'section': 'Packages',              'created_date': (now - timedelta(days=5)).isoformat(),   'created_by': 'SF Admin', 'display': 'Installed package: Education Data Architecture v2.4'},
    ]


def get_audit_trail(org: str, days: int = 7) -> list:
    """Query SetupAuditTrail for recent org config changes."""
    sf = get_sf(org)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    soql = (
        f"SELECT Id, Action, Section, CreatedDate, CreatedBy.Name, Display "
        f"FROM SetupAuditTrail "
        f"WHERE CreatedDate >= {since} "
        f"ORDER BY CreatedDate DESC LIMIT 200"
    )
    result = sf.query(soql)
    entries = []
    for r in result.get('records', []):
        creator = r.get('CreatedBy') or {}
        entries.append({
            'id': r.get('Id'),
            'action': r.get('Action', ''),
            'section': r.get('Section', ''),
            'created_date': r.get('CreatedDate'),
            'created_by': creator.get('Name', ''),
            'display': r.get('Display', ''),
        })
    if Config.SHOW_MOCK and not entries:
        return _mock_audit_trail()
    return entries


# ── Apex Job Queue ─────────────────────────────────────────────────────────────

def _job_status_flag(status: str) -> str:
    return {
        'Processing': 'primary', 'Preparing': 'info',
        'Queued': 'warning', 'Holding': 'warning',
        'Completed': 'success', 'Aborted': 'secondary',
        'Failed': 'danger',
    }.get(status, 'secondary')


def _mock_apex_jobs():
    now = datetime.now(timezone.utc)
    return [
        {'id': 'J001', 'class_name': 'MigrationBatchAccount',  'job_type': 'BatchApex',    'status': 'Completed',  'status_flag': 'success', 'created_date': (now - timedelta(hours=1)).isoformat(),               'completed_date': (now - timedelta(minutes=45)).isoformat(),              'items_processed': 4312, 'total_items': 4312, 'errors': 0, 'extended_status': '',                                            'created_by': 'Migration Service'},
        {'id': 'J002', 'class_name': 'ContactPointSyncBatch',  'job_type': 'BatchApex',    'status': 'Processing', 'status_flag': 'primary', 'created_date': (now - timedelta(minutes=10)).isoformat(),              'completed_date': None,                                                   'items_processed': 1240, 'total_items': 3800, 'errors': 0, 'extended_status': '',                                            'created_by': 'Migration Service'},
        {'id': 'J003', 'class_name': 'EthosGuidSyncQueueable', 'job_type': 'Queueable',    'status': 'Failed',     'status_flag': 'danger',  'created_date': (now - timedelta(hours=3)).isoformat(),                 'completed_date': (now - timedelta(hours=2, minutes=50)).isoformat(),     'items_processed': 0,    'total_items': 0,    'errors': 1, 'extended_status': 'System.LimitException: Too many SOQL queries: 101', 'created_by': 'SF Admin'},
        {'id': 'J004', 'class_name': 'DailyReadinessCheck',    'job_type': 'ScheduledApex', 'status': 'Queued',    'status_flag': 'warning', 'created_date': (now - timedelta(minutes=2)).isoformat(),               'completed_date': None,                                                   'items_processed': 0,    'total_items': 0,    'errors': 0, 'extended_status': '',                                            'created_by': 'SF Admin'},
    ]


def get_apex_job_queue(org: str, limit: int = 100) -> list:
    sf = get_sf(org)
    soql = (
        f"SELECT Id, ApexClass.Name, JobType, Status, CreatedDate, CompletedDate, "
        f"NumberOfErrors, JobItemsProcessed, TotalJobItems, ExtendedStatus, "
        f"CreatedBy.Name "
        f"FROM AsyncApexJob "
        f"WHERE JobType IN ('BatchApex','Queueable','ScheduledApex','Future') "
        f"ORDER BY CreatedDate DESC LIMIT {limit}"
    )
    result = sf.query(soql)
    jobs = []
    for r in result.get('records', []):
        cls = r.get('ApexClass') or {}
        creator = r.get('CreatedBy') or {}
        status = r.get('Status', '')
        jobs.append({
            'id': r.get('Id'),
            'class_name': cls.get('Name', ''),
            'job_type': r.get('JobType', ''),
            'status': status,
            'status_flag': _job_status_flag(status),
            'created_date': r.get('CreatedDate'),
            'completed_date': r.get('CompletedDate'),
            'items_processed': r.get('JobItemsProcessed', 0),
            'total_items': r.get('TotalJobItems', 0),
            'errors': r.get('NumberOfErrors', 0),
            'extended_status': r.get('ExtendedStatus') or '',
            'created_by': creator.get('Name', ''),
        })
    if Config.SHOW_MOCK and not jobs:
        return _mock_apex_jobs()
    return jobs


# ── Login History ──────────────────────────────────────────────────────────────

def _mock_login_history():
    now = datetime.now(timezone.utc)
    logins = [
        {'id': 'L001', 'user_id': 'U001', 'login_time': (now - timedelta(minutes=5)).isoformat(),              'source_ip': '198.51.100.10', 'platform': 'Web', 'application': 'Browser', 'login_type': 'Application', 'browser': 'Chrome 120',  'status': 'Success',              'success': True},
        {'id': 'L002', 'user_id': 'U002', 'login_time': (now - timedelta(hours=1)).isoformat(),                'source_ip': '198.51.100.10', 'platform': 'Web', 'application': 'Browser', 'login_type': 'Application', 'browser': 'Chrome 120',  'status': 'Success',              'success': True},
        {'id': 'L003', 'user_id': 'U003', 'login_time': (now - timedelta(hours=2)).isoformat(),                'source_ip': '203.0.113.55',  'platform': 'API', 'application': 'API',     'login_type': 'OAuth2',      'browser': '',            'status': 'Success',              'success': True},
        {'id': 'L004', 'user_id': 'U002', 'login_time': (now - timedelta(hours=3)).isoformat(),                'source_ip': '10.0.0.99',     'platform': 'Web', 'application': 'Browser', 'login_type': 'Application', 'browser': 'Firefox 121', 'status': 'Failed: Wrong Password', 'success': False},
        {'id': 'L005', 'user_id': 'U002', 'login_time': (now - timedelta(hours=3, minutes=2)).isoformat(),     'source_ip': '10.0.0.99',     'platform': 'Web', 'application': 'Browser', 'login_type': 'Application', 'browser': 'Firefox 121', 'status': 'Failed: Wrong Password', 'success': False},
    ]
    return {'logins': logins, 'summary': {'total': len(logins), 'failed': 2, 'unique_ips': 3, 'unique_users': 3}}


def get_login_history(org: str, limit: int = 200) -> dict:
    sf = get_sf(org)
    soql = (
        f"SELECT Id, UserId, LoginTime, SourceIp, Platform, Application, "
        f"LoginType, Status, Browser "
        f"FROM LoginHistory "
        f"ORDER BY LoginTime DESC LIMIT {limit}"
    )
    result = sf.query(soql)
    logins = []
    failed = 0
    unique_ips = set()
    unique_users = set()
    for r in result.get('records', []):
        status = r.get('Status', '')
        success = status == 'Success'
        if not success:
            failed += 1
        ip = r.get('SourceIp', '')
        uid = r.get('UserId', '')
        unique_ips.add(ip)
        unique_users.add(uid)
        logins.append({
            'id': r.get('Id'),
            'user_id': uid,
            'login_time': r.get('LoginTime'),
            'source_ip': ip,
            'platform': r.get('Platform', ''),
            'application': r.get('Application', ''),
            'login_type': r.get('LoginType', ''),
            'browser': r.get('Browser', ''),
            'status': status,
            'success': success,
        })
    if Config.SHOW_MOCK and not logins:
        return _mock_login_history()
    return {
        'logins': logins,
        'summary': {
            'total': len(logins),
            'failed': failed,
            'unique_ips': len(unique_ips),
            'unique_users': len(unique_users),
        }
    }
