"""Tag Sync — push app-level tags up to a Salesforce field.

SCAFFOLD ONLY (not yet implemented). The contract lives here so the future
implementation has a fixed shape and the rest of the app can call into it
with a clean "not yet" error in the meantime.

When wired up, this will let an operator promote interface-only tags (see
``services/tags.py``) into a real Salesforce multi-select picklist (or a
junction object), so other tools / users see the tag without depending on
this app's database.

Design intent for the eventual implementation:
- ``Config.TAG_SF_FIELD`` names the destination field (e.g. ``MC_Tags__c``
  on ``Account``). If blank, sync is disabled.
- ``sync_tags_to_sf(org, artifact_type='record', sf_id=..., tag_names=[...])``
  bulk-upserts the tag values on the given record(s) via the Bulk API 2.0.
- ``pull_tags_from_sf(org, sf_id)`` reads the field back and reconciles with
  the local ``artifact_tags`` rows so the two views stay in agreement.
- An honest-error path: if the field does not exist on the target SObject,
  raise ``RuntimeError('configure Config.TAG_SF_FIELD ...')`` rather than
  silently writing nothing.

Until the wiring lands, every entry point here raises so callers can't
accidentally rely on a half-baked sync.
"""
from config import Config

# Sentinel exposed to the UI so it can hide the "Sync to Salesforce" affordance
# instead of letting the user click a button that always errors. Update this to
# True together with implementing the functions below.
SYNC_AVAILABLE = False


def is_configured() -> bool:
    """True when an admin has named a destination field in Config.TAG_SF_FIELD."""
    return bool(Config.TAG_SF_FIELD)


def sync_tags_to_sf(org: str, sf_id: str, tag_names: list) -> dict:
    """Write the given tag values to Config.TAG_SF_FIELD on the SF record.

    NOT YET IMPLEMENTED. See module docstring for the planned contract.
    """
    raise NotImplementedError(
        'Tag Sync to Salesforce is not yet implemented. Configure '
        'Config.TAG_SF_FIELD and finish services/tag_sync.py before enabling '
        'the Sync to Salesforce UI affordance.'
    )


def pull_tags_from_sf(org: str, sf_id: str) -> list:
    """Read tags from Config.TAG_SF_FIELD on the SF record and return their names.

    NOT YET IMPLEMENTED. See module docstring for the planned contract.
    """
    raise NotImplementedError(
        'Tag Sync from Salesforce is not yet implemented.'
    )
