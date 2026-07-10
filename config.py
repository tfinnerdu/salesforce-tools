import os
from dotenv import load_dotenv

load_dotenv()


def get_org_config(org: str = 'dev') -> dict:
    """Return SF credential dict for the given org name."""
    prefix = f"SF_{org.upper()}_"
    return {
        'username': os.environ.get(f'{prefix}USERNAME', ''),
        'password': os.environ.get(f'{prefix}PASSWORD', ''),
        'security_token': os.environ.get(f'{prefix}TOKEN', ''),
        'domain': os.environ.get(f'{prefix}DOMAIN', 'login'),
        'api_version': os.environ.get(f'{prefix}API_VERSION') or os.environ.get('SF_API_VERSION', '59.0'),
    }


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/sf_mission_control')
    CONDUCTOR_URL = os.environ.get('CONDUCTOR_URL', 'http://conductor:8080')
    CONDUCTOR_API_KEY = os.environ.get('CONDUCTOR_API_KEY', '')
    # SHOW_MOCK=true swaps in the MockSalesforce + MockConductorClient layer
    # for the entire app — intended for manual UI/demo testing when real
    # credentials are unavailable. All-or-nothing: there is no per-system
    # mock toggle. Default false; the production path requires real creds.
    SHOW_MOCK = os.environ.get('SHOW_MOCK', 'false').lower() == 'true'
    # Shared secret that Argo (or any scheduler) must present on the
    # /scenarios/<id>/scheduled-run endpoint. Blank = scheduled runs disabled.
    SCHEDULER_TOKEN = os.environ.get('SCHEDULER_TOKEN', '')
    # Externally-reachable base URL, used when generating Argo CronWorkflow
    # manifests so the curl target is correct. Defaults to the prod ingress.
    PUBLIC_BASE_URL = os.environ.get(
        'PUBLIC_BASE_URL', 'https://du-int.doane.edu/prod/sf-mission-control')
    DEFAULT_ORG = os.environ.get('DEFAULT_ORG', 'dev')
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false').lower() == 'true'
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'false').lower() == 'true'
    BACKUP_RETAIN = int(os.environ.get('BACKUP_RETAIN', '14'))
    # Total records expected in the migration. Drives velocity %-complete / ETA.
    # 0 = unknown (the velocity view degrades gracefully).
    MIGRATION_RECORD_TARGET = int(os.environ.get('MIGRATION_RECORD_TARGET', '0'))
    SQLSERVER_CONN = os.environ.get('SQLSERVER_CONN', '')
    PORT = int(os.environ.get('PORT', 5000))
    VERSION = '1.0.0'
    SF_DML_RATE_LIMIT = int(os.environ.get('SF_DML_RATE_LIMIT', '0'))
    SF_BYPASS_SETTING = os.environ.get('SF_BYPASS_SETTING', '')
    SF_BYPASS_FIELD = os.environ.get('SF_BYPASS_FIELD', 'Bypass_Triggers__c')
    # Salesforce SOAP login rejects API versions above ~59.0; REST calls use SF_API_VERSION.
    SF_SOAP_AUTH_VERSION = os.environ.get('SF_SOAP_AUTH_VERSION', '57.0')
    PII_SERVICE_URL = os.environ.get('PII_SERVICE_URL', '')
    # Salesforce field used by the (future) Tag Sync — when set, app-level
    # tags applied to records can be pushed up to this field on the target
    # SObject. Multi-select picklist or text. Leave blank to keep tags
    # interface-only. See services/tag_sync.py.
    TAG_SF_FIELD = os.environ.get('TAG_SF_FIELD', '')
