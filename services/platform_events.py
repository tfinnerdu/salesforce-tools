"""Platform Events — PlatformEventChannel and PlatformEventChannelMember."""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)


# ── Platform Event Channels ───────────────────────────────────────────────────

_PE_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel "
    "FROM PlatformEventChannel ORDER BY MasterLabel"
)


def _map_event(r: dict) -> dict:
    return {
        'id': r.get('Id'),
        'developer_name': r.get('DeveloperName', ''),
        'label': r.get('MasterLabel', ''),
    }


def get_platform_events(org: str) -> list:
    """Query PlatformEventChannel via Tooling API."""
    sf = get_sf(org)
    result = sf.restful('tooling/query/', params={'q': _PE_SOQL})
    records = result.get('records', [])
    return [_map_event(r) for r in records]


# ── Platform Event Channel Members ────────────────────────────────────────────

_PEM_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel, EventChannel "
    "FROM PlatformEventChannelMember ORDER BY DeveloperName"
)


def _map_member(r: dict) -> dict:
    # EventChannel is a plain text field holding the channel's API name —
    # NOT a relationship, so EventChannel.DeveloperName is invalid.
    return {
        'id': r.get('Id'),
        'developer_name': r.get('DeveloperName', ''),
        'channel': r.get('EventChannel', '') or '',
        'type': '',
    }


def get_event_members(org: str) -> list:
    """Query PlatformEventChannelMember (subscriptions) via Tooling API."""
    sf = get_sf(org)
    result = sf.restful('tooling/query/', params={'q': _PEM_SOQL})
    records = result.get('records', [])
    return [_map_member(r) for r in records]


# ── Convenience ───────────────────────────────────────────────────────────────

def get_all(org: str) -> dict:
    return {
        'events': get_platform_events(org),
        'members': get_event_members(org),
    }
