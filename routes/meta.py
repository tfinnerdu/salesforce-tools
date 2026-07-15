"""Meta blueprint — shared describe-driven metadata for the app-wide object picker.

One canonical object-list endpoint so every tab's object field is fed from the
same source instead of each tab hardcoding, freetext-ing, or re-querying its
own list. `GET /meta/objects` returns the org's full SObject list plus the
DescribeGlobal capability flags (queryable / layoutable / createable /
updateable / deletable); the front-end `MC.objectPicker` filters that one list
per context — SOQL to `queryable`, the CLI field builder to `customizable`
(`layoutable`), Data Ops DML to `updateable`/`deletable`, etc. — so an object
only appears where the action can actually succeed.

Read-only. Backed by `services.cli_metadata` (the app's reusable describe
layer). Uses the shared error envelope (utils.responses); `g.request_id` is set
per request. Routing follows this app's blueprint-prefix convention.
"""
import logging

from flask import Blueprint, session

from config import Config
from services import cli_metadata
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# This blueprint has no HTML page of its own (it only ever served JSON), so
# meta_bp survives solely as the legacy /meta/<subpath> -> /api/v1/meta/<subpath>
# 308 redirect; the real logic lives on meta_api_bp.
meta_bp = Blueprint('meta', __name__, url_prefix='/meta')
meta_api_bp = Blueprint('meta_api', __name__, url_prefix='/api/v1/meta')

register_legacy_json_redirect(meta_bp, '/api/v1/meta')


@meta_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


def _org() -> str:
    return session.get('active_org', Config.DEFAULT_ORG)


@meta_api_bp.route('/objects')
def api_objects():
    """The org's SObjects with capability flags, A→Z (shared picker source)."""
    try:
        return ok(cli_metadata.list_objects(_org()))
    except Exception as exc:
        logger.exception('meta objects list failed')
        return error_response(str(exc), 'SF_DESCRIBE_FAILED', 502)
