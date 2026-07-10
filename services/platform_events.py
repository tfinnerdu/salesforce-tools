"""Platform Events — PlatformEventChannel and PlatformEventChannelMember."""
import logging

from config import Config
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


def _mock_events() -> list:
    return [
        {'id': '0..1', 'developer_name': 'Migration_Complete__e', 'label': 'Migration Complete'},
        {'id': '0..2', 'developer_name': 'Student_Update__e',    'label': 'Student Update'},
        {'id': '0..3', 'developer_name': 'Ethos_Error__e',       'label': 'Ethos Error'},
    ]


def get_platform_events(org: str) -> list:
    """Query PlatformEventChannel via Tooling API."""
    sf = get_sf(org)
    try:
        result = sf.restful('tooling/query/', params={'q': _PE_SOQL})
        records = result.get('records', [])
        if Config.SHOW_MOCK and not records:
            return _mock_events()
        return [_map_event(r) for r in records]
    except Exception:
        if Config.SHOW_MOCK:
            return _mock_events()
        raise


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


def _mock_members() -> list:
    return [
        {'id': '0..4', 'developer_name': 'MigrationComplete_Flow',   'channel': 'Migration_Complete__e', 'type': 'Flow'},
        {'id': '0..5', 'developer_name': 'StudentUpdate_Trigger',     'channel': 'Student_Update__e',     'type': 'ApexTrigger'},
        {'id': '0..6', 'developer_name': 'EthosError_EmailAlert',     'channel': 'Ethos_Error__e',        'type': 'WorkflowAlert'},
    ]


def get_event_members(org: str) -> list:
    """Query PlatformEventChannelMember (subscriptions) via Tooling API."""
    sf = get_sf(org)
    try:
        result = sf.restful('tooling/query/', params={'q': _PEM_SOQL})
        records = result.get('records', [])
        if Config.SHOW_MOCK and not records:
            return _mock_members()
        return [_map_member(r) for r in records]
    except Exception:
        if Config.SHOW_MOCK:
            return _mock_members()
        raise


# ── Convenience ───────────────────────────────────────────────────────────────

def get_all(org: str) -> dict:
    return {
        'events': get_platform_events(org),
        'members': get_event_members(org),
    }
