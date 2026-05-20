"""Integration Inventory — Named Credentials, Remote Site Settings, Connected Apps."""
import logging

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)


# ── Named Credentials ─────────────────────────────────────────────────────────

_NC_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel, Endpoint, Protocol, PrincipalType "
    "FROM NamedCredential ORDER BY MasterLabel"
)


def _map_named_cred(r: dict) -> dict:
    return {
        'id': r.get('Id'),
        'developer_name': r.get('DeveloperName', ''),
        'master_label': r.get('MasterLabel', ''),
        'endpoint': r.get('Endpoint', ''),
        'protocol': r.get('Protocol', ''),
        'principal_type': r.get('PrincipalType', ''),
    }


def _mock_named_credentials() -> list:
    return [
        {
            'id': 'NC001',
            'developer_name': 'ConductorAPI',
            'master_label': 'Conductor API',
            'endpoint': 'https://conductor.doane.edu/api',
            'protocol': 'Named Principal',
            'principal_type': 'NamedUser',
        },
        {
            'id': 'NC002',
            'developer_name': 'EthosIntegrationHub',
            'master_label': 'Ethos Integration Hub',
            'endpoint': 'https://ethos.ellucian.com/api',
            'protocol': 'Named Principal',
            'principal_type': 'NamedUser',
        },
        {
            'id': 'NC003',
            'developer_name': 'AWSS3Archive',
            'master_label': 'AWS S3 Archive',
            'endpoint': 'https://s3.amazonaws.com/doane-archive',
            'protocol': 'Named Principal',
            'principal_type': 'NamedUser',
        },
    ]


def get_named_credentials(org: str) -> list:
    """Query NamedCredential via Tooling API."""
    sf = get_sf(org)
    try:
        result = sf.restful('tooling/query/', params={'q': _NC_SOQL})
        records = result.get('records', [])
        if Config.SF_MOCK and not records:
            return _mock_named_credentials()
        return [_map_named_cred(r) for r in records]
    except Exception:
        if Config.SF_MOCK:
            return _mock_named_credentials()
        raise


# ── Remote Site Settings ──────────────────────────────────────────────────────

_RSS_SOQL = (
    "SELECT Id, SiteName, Description, Url, IsActive, DisableProtocolSecurity "
    "FROM RemoteSiteSetting ORDER BY SiteName"
)


def _map_remote_site(r: dict) -> dict:
    return {
        'id': r.get('Id'),
        'site_name': r.get('SiteName', ''),
        'description': r.get('Description', ''),
        'url': r.get('Url', ''),
        'is_active': bool(r.get('IsActive', False)),
        'disable_protocol_security': bool(r.get('DisableProtocolSecurity', False)),
    }


def _mock_remote_sites() -> list:
    return [
        {
            'id': 'RSS001',
            'site_name': 'Conductor',
            'description': 'Conductor integration hub',
            'url': 'https://conductor.doane.edu',
            'is_active': True,
            'disable_protocol_security': False,
        },
        {
            'id': 'RSS002',
            'site_name': 'Ethos',
            'description': 'Ellucian Ethos API',
            'url': 'https://ethos.ellucian.com',
            'is_active': True,
            'disable_protocol_security': False,
        },
        {
            'id': 'RSS003',
            'site_name': 'Colleague',
            'description': 'Colleague SIS endpoint',
            'url': 'https://colleague.doane.edu',
            'is_active': True,
            'disable_protocol_security': False,
        },
        {
            'id': 'RSS004',
            'site_name': 'S3',
            'description': 'AWS S3 archive bucket',
            'url': 'https://s3.amazonaws.com',
            'is_active': True,
            'disable_protocol_security': False,
        },
    ]


def get_remote_sites(org: str) -> list:
    """Query RemoteSiteSetting via Tooling API."""
    sf = get_sf(org)
    try:
        result = sf.restful('tooling/query/', params={'q': _RSS_SOQL})
        records = result.get('records', [])
        if Config.SF_MOCK and not records:
            return _mock_remote_sites()
        return [_map_remote_site(r) for r in records]
    except Exception:
        if Config.SF_MOCK:
            return _mock_remote_sites()
        raise


# ── Connected Apps ────────────────────────────────────────────────────────────

_CA_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel, Description "
    "FROM ConnectedApplication ORDER BY MasterLabel"
)


def _map_connected_app(r: dict) -> dict:
    return {
        'id': r.get('Id'),
        'developer_name': r.get('DeveloperName', ''),
        'master_label': r.get('MasterLabel', ''),
        'description': r.get('Description', ''),
    }


def _mock_connected_apps() -> list:
    return [
        {
            'id': 'CA001',
            'developer_name': 'MigrationTools',
            'master_label': 'Doane SF Migration Tools',
            'description': 'OAuth connected app for the SF Mission Control migration pipeline.',
        },
        {
            'id': 'CA002',
            'developer_name': 'WorkatoConnector',
            'master_label': 'Workato Integration',
            'description': 'Connected app for Workato iPaaS integration recipes.',
        },
    ]


def get_connected_apps(org: str) -> list:
    """Query ConnectedApplication via Tooling API."""
    sf = get_sf(org)
    try:
        result = sf.restful('tooling/query/', params={'q': _CA_SOQL})
        records = result.get('records', [])
        if Config.SF_MOCK and not records:
            return _mock_connected_apps()
        return [_map_connected_app(r) for r in records]
    except Exception:
        if Config.SF_MOCK:
            return _mock_connected_apps()
        raise


# ── Convenience ───────────────────────────────────────────────────────────────

def get_all(org: str) -> dict:
    return {
        'named_credentials': get_named_credentials(org),
        'remote_sites': get_remote_sites(org),
        'connected_apps': get_connected_apps(org),
    }
