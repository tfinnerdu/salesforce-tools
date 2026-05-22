"""Integration Inventory — Named Credentials, Remote Site Settings, Connected Apps."""
import logging

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


def get_named_credentials(org: str) -> list:
    """Query NamedCredential via Tooling API."""
    sf = get_sf(org)
    result = sf.restful('tooling/query/', params={'q': _NC_SOQL})
    records = result.get('records', [])
    return [_map_named_cred(r) for r in records]


# ── Remote Site Settings ──────────────────────────────────────────────────────

_RSS_SOQL = (
    "SELECT Id, SiteName, Description, EndpointUrl, IsActive "
    "FROM RemoteSiteSetting ORDER BY SiteName"
)


def _map_remote_site(r: dict) -> dict:
    # DisableProtocolSecurity is not a queryable column on the RemoteProxy
    # entity (it lives inside Metadata) — not surfaced here.
    return {
        'id': r.get('Id'),
        'site_name': r.get('SiteName', ''),
        'description': r.get('Description', ''),
        'url': r.get('EndpointUrl', ''),
        'is_active': bool(r.get('IsActive', False)),
        'disable_protocol_security': False,
    }


def get_remote_sites(org: str) -> list:
    """Query RemoteSiteSetting via Tooling API."""
    sf = get_sf(org)
    result = sf.restful('tooling/query/', params={'q': _RSS_SOQL})
    records = result.get('records', [])
    return [_map_remote_site(r) for r in records]


# ── Connected Apps ────────────────────────────────────────────────────────────

_CA_SOQL = "SELECT Id, Name FROM ConnectedApplication ORDER BY Name"


def _map_connected_app(r: dict) -> dict:
    name = r.get('Name', '')
    return {
        'id': r.get('Id'),
        'developer_name': name,   # Data API doesn't expose DeveloperName separately
        'master_label': name,
        'description': '',
    }


def get_connected_apps(org: str) -> list:
    """Query ConnectedApplication via the standard Data API (not Tooling API).

    ConnectedApplication is not a Tooling API object — querying it through
    tooling/query returns INVALID_TYPE. The Data API object exposes Id and Name
    only; DeveloperName and Description are not available on this endpoint.
    """
    sf = get_sf(org)
    try:
        result = sf.query(_CA_SOQL)
        records = result.get('records', [])
        return [_map_connected_app(r) for r in records]
    except Exception as exc:
        # ConnectedApplication needs an elevated permission ("Manage Connected
        # Apps" / "Customize Application"). Without it the query fails with
        # INSUFFICIENT_ACCESS; if the object is unavailable it fails with
        # INVALID_TYPE. Either way, degrade to an empty list so the rest of the
        # Integration Inventory page still loads.
        text = str(exc)
        if 'INSUFFICIENT_ACCESS' in text or 'INVALID_TYPE' in text:
            logger.warning('connected apps unavailable for org %s: %s', org, exc)
            return []
        raise


# ── Convenience ───────────────────────────────────────────────────────────────

def get_all(org: str) -> dict:
    return {
        'named_credentials': get_named_credentials(org),
        'remote_sites': get_remote_sites(org),
        'connected_apps': get_connected_apps(org),
    }
