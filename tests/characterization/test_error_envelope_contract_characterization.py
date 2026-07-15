"""
Characterization tests — the shared error-response envelope contract.

Pins the Doane standard's required non-2xx JSON shape:
{"error": "<message>", "code": "<MACHINE_CODE>", "request_id": "<uuid-or-unknown>"}

utils.responses.error_response() is the one shared helper meant to produce
this shape everywhere (today adopted by routes/cli.py and routes/meta.py;
the other 13 blueprints still build error JSON inline -- see CLAUDE.md's
"API-shape note" for that tracked, deliberate follow-up). This file pins the
contract of the helper itself, plus confirms a real CLI-blueprint error path
actually returns it -- so if a future refactor of routes/cli.py or
utils/responses.py silently drops a field, this fails and names the change.
"""
import json

from utils.responses import error_response


def test_error_response_shape_characterization(app):
    with app.test_request_context('/'):
        resp, status = error_response('Something went wrong', 'INVALID_INPUT', 400)
        body = json.loads(resp.get_data(as_text=True))
    assert status == 400
    assert body['success'] is False
    assert body['error'] == 'Something went wrong'
    assert body['code'] == 'INVALID_INPUT', 'code must be a machine-readable string, never a raw status number.'
    assert 'request_id' in body
    assert body['request_id'] != ''


def test_error_response_code_is_never_a_bare_number_characterization(app):
    with app.test_request_context('/'):
        resp, status = error_response('x', 'SF_DESCRIBE_FAILED', 502)
        body = json.loads(resp.get_data(as_text=True))
    assert not str(body['code']).isdigit(), 'code must be a machine string like "SF_DESCRIBE_FAILED", not "502".'


def test_error_response_falls_back_to_unknown_request_id_outside_before_request(app):
    # No before_request hook ran to set g.request_id in this bare context.
    with app.test_request_context('/'):
        resp, _ = error_response('x', 'X', 400)
        body = json.loads(resp.get_data(as_text=True))
    assert body['request_id'] == 'unknown'


def test_error_response_threads_g_request_id_when_set(app):
    from flask import g
    with app.test_request_context('/'):
        g.request_id = 'abc-123'
        resp, _ = error_response('x', 'X', 400)
        body = json.loads(resp.get_data(as_text=True))
    assert body['request_id'] == 'abc-123'


def test_live_cli_route_error_matches_envelope_contract_characterization(client):
    # A real CLI-blueprint error path (missing required "object") must return
    # the exact contract, not just utils.responses in isolation.
    resp = client.post('/cli/clone-object/plan', data=json.dumps({}),
                       content_type='application/json')
    assert resp.status_code == 400
    body = resp.get_json()
    for key in ('error', 'code', 'request_id'):
        assert key in body, f'/cli/clone-object/plan error response missing required key "{key}"'
    assert not str(body['code']).isdigit()
