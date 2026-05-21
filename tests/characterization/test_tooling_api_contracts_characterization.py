"""
Characterization tests — Salesforce Tooling/Data API query contracts.

These pin the corrected SF API field names and endpoints discovered during
the May 2026 "malformed request" bug sweep. Each query below produced a real
INVALID_FIELD / INVALID_TYPE error against the doanefull sandbox before it was
fixed. The hardcoded known-good values are the documentation of the fix.

If one of these tests fails, the SF API contract assumption in the code has
changed. Verify the change is intentional against a live org's Tooling API
WSDL / describe before updating the hardcoded value.

These do NOT call a live org — they pin what the code assumes the contract to be.
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# RemoteSiteSetting — the URL field is 'EndpointUrl', not 'Url'.
#
# RemoteSiteSetting resolves to the RemoteProxy entity in the Tooling API.
# RemoteProxy has no 'Url' column — the URL field is 'EndpointUrl'. It also
# has no 'DisableProtocolSecurity' column (that lives inside Metadata) —
# querying it returns INVALID_FIELD. Both fixes verified against the
# doanefull sandbox. Fixed: May 2026.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_RSS_SOQL = (
    "SELECT Id, SiteName, Description, EndpointUrl, IsActive "
    "FROM RemoteSiteSetting ORDER BY SiteName"
)


def test_remote_site_setting_query_uses_endpointurl_characterization():
    from services.integration_inventory import _RSS_SOQL
    assert _RSS_SOQL == KNOWN_RSS_SOQL, (
        "The RemoteSiteSetting Tooling API query has changed. The backing "
        "RemoteProxy entity uses 'EndpointUrl' (not 'Url') and has no "
        "'DisableProtocolSecurity' column. If this changed intentionally, "
        "verify against the org's Tooling API describe before updating."
    )
    assert 'DisableProtocolSecurity' not in _RSS_SOQL
    assert ' Url ' not in _RSS_SOQL


# ─────────────────────────────────────────────────────────────────────────────
# PlatformEventChannelMember — 'EventChannel' is a plain text field, not a
# relationship. Querying EventChannel.DeveloperName returns:
#   "Didn't understand relationship 'EventChannel' in field path" (INVALID_FIELD)
# There is also no 'Type' column. Fixed: May 2026.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_PEM_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel, EventChannel "
    "FROM PlatformEventChannelMember ORDER BY DeveloperName"
)


def test_platform_event_channel_member_query_characterization():
    from services.platform_events import _PEM_SOQL
    assert _PEM_SOQL == KNOWN_PEM_SOQL, (
        "The PlatformEventChannelMember query changed. 'EventChannel' is a text "
        "field, not a relationship — 'EventChannel.DeveloperName' is invalid."
    )
    assert 'EventChannel.' not in _PEM_SOQL


# ─────────────────────────────────────────────────────────────────────────────
# PlatformEventChannel — has NO 'Description' field.
#
# Querying Description returns:
#   "No such column 'Description' on entity 'PlatformEventChannel'" (INVALID_FIELD)
# Valid columns: Id, DeveloperName, MasterLabel, NamespacePrefix, ChannelType.
# Fixed: May 2026.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_PE_SOQL = (
    "SELECT Id, DeveloperName, MasterLabel "
    "FROM PlatformEventChannel ORDER BY MasterLabel"
)


def test_platform_event_channel_query_omits_description_characterization():
    from services.platform_events import _PE_SOQL
    assert _PE_SOQL == KNOWN_PE_SOQL, (
        "The PlatformEventChannel Tooling API query has changed. This entity has "
        "no 'Description' column — including it fails with INVALID_FIELD. If this "
        "changed intentionally, verify against the org's Tooling API describe."
    )
    assert 'Description' not in _PE_SOQL


# ─────────────────────────────────────────────────────────────────────────────
# ProcessException — queried via the Data API, NOT the Tooling API.
#
# ProcessException is an Order Management standard object. It is not exposed by
# the Tooling API — querying tooling/query/ returns:
#   "sObject type 'ProcessException' is not supported" (INVALID_TYPE)
# It must be queried via the regular Data API (sf.query). When Order Management
# is not enabled the object does not exist at all, so the service degrades
# gracefully to an empty list. Fixed: May 2026.
# ─────────────────────────────────────────────────────────────────────────────

class _SpySF:
    """Records which API surface list_process_exceptions used."""
    def __init__(self, raise_exc=None):
        self.query_soql = None
        self.restful_called = False
        self._raise_exc = raise_exc

    def query(self, soql):
        self.query_soql = soql
        if self._raise_exc:
            raise self._raise_exc
        return {'records': []}

    def restful(self, *a, **kw):
        self.restful_called = True
        raise AssertionError('ProcessException must NOT be queried via the Tooling API')


def test_process_exception_uses_data_api_not_tooling_characterization(monkeypatch):
    import services.apex_log_reader as alr
    spy = _SpySF()
    monkeypatch.setattr(alr, 'get_sf', lambda org: spy)

    result = alr.list_process_exceptions('dev')

    assert result == []
    assert spy.restful_called is False, (
        "ProcessException was queried via the Tooling API (restful). It is not a "
        "Tooling API object — it must be queried via the Data API (sf.query)."
    )
    assert spy.query_soql is not None, "ProcessException was not queried via the Data API"
    assert 'FROM ProcessException' in spy.query_soql


def test_process_exception_invalid_type_degrades_gracefully_characterization(monkeypatch):
    """When Order Management is off, ProcessException does not exist — return []."""
    import services.apex_log_reader as alr
    spy = _SpySF(raise_exc=Exception(
        "INVALID_TYPE: sObject type 'ProcessException' is not supported"))
    monkeypatch.setattr(alr, 'get_sf', lambda org: spy)

    assert alr.list_process_exceptions('dev') == [], (
        "An INVALID_TYPE error for ProcessException must degrade to an empty list, "
        "not surface as a 'Malformed request' error to the user."
    )


def test_process_exception_unexpected_error_still_raises_characterization(monkeypatch):
    """A non-INVALID_TYPE error must NOT be swallowed — only the OM-absent case is."""
    import services.apex_log_reader as alr
    spy = _SpySF(raise_exc=RuntimeError('connection reset'))
    monkeypatch.setattr(alr, 'get_sf', lambda org: spy)

    with pytest.raises(RuntimeError, match='connection reset'):
        alr.list_process_exceptions('dev')


# ─────────────────────────────────────────────────────────────────────────────
# FlowInterview — queried via the Data API, NOT the Tooling API.
#   tooling/query/ FROM FlowInterview -> "sObject type 'FlowInterview' is not
#   supported" (INVALID_TYPE). Fixed: May 2026.
#
# Flows are listed via FlowDefinitionView (Data API). FlowDefinition (the
# Tooling object) has no ProcessType or Status columns -> INVALID_FIELD.
# ─────────────────────────────────────────────────────────────────────────────

class _FlowSpySF:
    """Records the Data API SOQL used; fails loudly if the Tooling API is hit."""
    def __init__(self):
        self.query_soql = None
        self.restful_called = False

    def query(self, soql):
        self.query_soql = soql
        return {'records': []}

    def restful(self, *a, **kw):
        self.restful_called = True
        raise AssertionError('this query must use the Data API, not the Tooling API')


def test_flow_errors_uses_data_api_characterization(monkeypatch):
    import services.apex_log_reader as alr
    spy = _FlowSpySF()
    monkeypatch.setattr(alr, 'get_sf', lambda org: spy)
    alr.list_flow_errors('dev')
    assert spy.restful_called is False
    assert spy.query_soql and 'FROM FlowInterview' in spy.query_soql, (
        "list_flow_errors must query FlowInterview via the Data API — it is not "
        "a Tooling API object."
    )


def test_org_automation_flows_use_flowdefinitionview_characterization(monkeypatch):
    import services.org_automation as oa
    spy = _FlowSpySF()
    monkeypatch.setattr(oa, 'get_sf', lambda org: spy)
    oa.get_flows('dev')
    assert spy.query_soql and 'FlowDefinitionView' in spy.query_soql, (
        "get_flows must query FlowDefinitionView (Data API) — FlowDefinition "
        "(Tooling) has no ProcessType/Status columns."
    )
