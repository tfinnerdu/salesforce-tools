"""
Characterization tests — API route contracts for the Data Ops tools,
Permissions Audit, and Automation & Sharing features added May 2026.

Pins each new route's URL path, method, success status, and top-level
response shape. If a route is renamed or its response envelope is
restructured, exactly one of these fails and names the broken contract.

The standard envelope for JSON API routes in this app is:
    {"success": bool, "data": <payload>}    on success
    {"success": false, "error": str}        on failure (HTTP 4xx/5xx)
"""
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# JSON API routes — GET, standard {success, data} envelope.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_GET_JSON_ROUTES = [
    '/admin/permissions/sets',
    '/admin/permissions/users',
    '/admin/permissions/user/005000000000000001',
    '/admin/permissions/set/0PS000000000000001',
    '/admin/permissions/object-matrix?object=Account',
    '/admin/permissions/field-matrix?object=Account',
    '/admin/automation/validation-rules',
    '/admin/automation/flows',
    '/admin/automation/triggers',
    '/admin/automation/sharing-model',
    '/data-ops/reassign/users?q=',
]


@pytest.mark.parametrize('path', KNOWN_GET_JSON_ROUTES)
def test_get_json_route_contract_characterization(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, (
        f"Route {path} no longer returns 200. If renamed/removed intentionally, "
        f"update KNOWN_GET_JSON_ROUTES."
    )
    body = resp.get_json()
    assert body is not None and 'success' in body and 'data' in body, (
        f"Route {path} no longer returns the standard {{success, data}} envelope."
    )
    assert body['success'] is True


# ─────────────────────────────────────────────────────────────────────────────
# Tool page routes — GET, HTML 200.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_PAGE_ROUTES = [
    '/data-ops/import',
    '/data-ops/export',
    '/data-ops/delete',
    '/data-ops/modify',
    '/data-ops/reassign',
]


@pytest.mark.parametrize('path', KNOWN_PAGE_ROUTES)
def test_tool_page_route_contract_characterization(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, (
        f"Tool page {path} no longer renders. If renamed intentionally, "
        f"update KNOWN_PAGE_ROUTES and the Data Ops sub-nav in every template."
    )


# ─────────────────────────────────────────────────────────────────────────────
# /data-ops/ index redirects to the Import tool (was Join Builder pre-May-2026).
# ─────────────────────────────────────────────────────────────────────────────

def test_data_ops_index_redirect_target_characterization(client):
    resp = client.get('/data-ops/')
    assert resp.status_code == 302
    assert 'import' in resp.headers['Location'], (
        "The /data-ops/ index redirect target changed. It points to the Import "
        "tool as of May 2026. Update this test if the landing tool changed."
    )


# ─────────────────────────────────────────────────────────────────────────────
# File-download routes — return text/csv with a Content-Disposition attachment.
# ─────────────────────────────────────────────────────────────────────────────

def test_export_route_returns_csv_attachment_characterization(client):
    resp = client.post('/data-ops/export/run',
                       json={'soql': 'SELECT Id FROM Account LIMIT 1', 'filename': 'e.csv'})
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type, (
        "/data-ops/export/run no longer returns text/csv. The export contract is "
        "a direct CSV file download, not a JSON envelope."
    )
    assert 'attachment' in resp.headers.get('Content-Disposition', '')


# ─────────────────────────────────────────────────────────────────────────────
# Import API contract — validate returns a row-count summary, execute returns
# success/error counts. These payload keys are consumed by the wizard UI.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_VALIDATE_KEYS = {'total_rows', 'clean_rows', 'warning_rows', 'error_rows',
                       'errors', 'summary', 'object_name', 'operation'}
KNOWN_EXECUTE_KEYS = {'success_count', 'error_count', 'total', 'results',
                      'error_csv', 'object_name', 'operation'}


def test_import_validate_payload_keys_characterization():
    from services import data_importer
    result = data_importer.validate_csv(
        'dev', 'Account', 'Name\nAlice\n', {'Name': 'Name'}, 'insert')
    assert KNOWN_VALIDATE_KEYS.issubset(result.keys()), (
        "data_importer.validate_csv result keys changed. The Import wizard step 3 "
        "UI consumes these exact keys — update the JS in mc-data-ops-snippet.js too."
    )


def test_import_execute_payload_keys_characterization():
    from services import data_importer
    result = data_importer.import_csv(
        'dev', 'Account', 'Name\nAlice\n', {'Name': 'Name'}, 'insert')
    assert KNOWN_EXECUTE_KEYS.issubset(result.keys()), (
        "data_importer.import_csv result keys changed. The Import wizard step 4 "
        "UI consumes these exact keys — update the JS in mc-data-ops-snippet.js too."
    )
