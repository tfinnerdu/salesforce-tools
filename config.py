import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _resolve_secret_key() -> str:
    """SECRET_KEY, with no publicly-known fallback constant.

    A hardcoded default (the old 'dev-secret-change-in-prod') let anyone forge
    session cookies if it ever reached production. Instead, when SECRET_KEY is
    unset we mint a random per-process key: sessions can't be forged, local dev
    still runs, and the warning makes a prod deploy that forgot to inject the
    secret visible in logs. Set SECRET_KEY in production so sessions survive
    restarts and are consistent across pods.
    """
    key = os.environ.get('SECRET_KEY', '')
    if key:
        return key
    logger.warning(
        'SECRET_KEY not set — using a random ephemeral key. Set SECRET_KEY in '
        'production (sessions will not persist across restarts or extra pods).'
    )
    return secrets.token_hex(32)


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
    SECRET_KEY = _resolve_secret_key()
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
    # Orgs exposed in the navbar picker + diff/CLI pickers. Comma-separated;
    # the single source of truth for which environments the app offers. Add a
    # name here (plus its SF_<NAME>_* credentials) to surface a new org.
    AVAILABLE_ORGS = [
        o.strip() for o in os.environ.get('AVAILABLE_ORGS', 'dev,prod,sandbox').split(',')
        if o.strip()
    ]
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
    # CLI tab (Salesforce CLI script generator) defaults. Doane-specific but
    # overridable via env so a peer institution can swap them without code
    # changes (Higher-Ed-agnostic posture). Prefilled into the builder as
    # editable fields, never baked into generated output.
    CLI_DEFAULT_INSTANCE_URL = os.environ.get(
        'CLI_DEFAULT_INSTANCE_URL',
        'https://doaneu--doanefull.sandbox.my.salesforce.com')
    CLI_PROJECT_BASE_PATH = os.environ.get(
        'CLI_PROJECT_BASE_PATH', 'C:\\Doane\\Code\\Salesforce-Projects')
    # Reusable starting values the CLI builder pre-fills as editable field
    # values (not just grey placeholders) — clear or change them as needed.
    CLI_DEFAULT_ALIAS = os.environ.get('CLI_DEFAULT_ALIAS', 'DoaneUAT')
    CLI_DEFAULT_PROJECT = os.environ.get('CLI_DEFAULT_PROJECT', 'doane-sf')
    CLI_DEFAULT_PERMSET = os.environ.get('CLI_DEFAULT_PERMSET', 'SF_Tools_Importer')
