"""Shared API response helpers.

Introduced with the CLI tab as the standards-conformant error envelope
(`{error, code, request_id}`), kept a superset of this app's existing
`{success, data}` / `{success:false, error}` envelope so the front-end
`MC.api` unwrapper keeps working unchanged.

A follow-up (see docs/user-guide.md CLI section) can adopt this helper across
the other blueprints and, if desired, move data/action routes under
`/api/v1/` — deliberately, not smuggled in via one feature.
"""
import uuid

from flask import g, jsonify


def new_request_id() -> str:
    """A fresh request id; store on flask.g in a blueprint before_request."""
    return uuid.uuid4().hex


def ok(data, status: int = 200):
    """Success envelope: {success: true, data: ...}."""
    return jsonify({'success': True, 'data': data}), status


def error_response(message: str, code: str, status: int = 400):
    """Standards error envelope, MC.api-compatible.

    Body: {success:false, error, code, request_id}. `code` is a machine
    string (e.g. 'INVALID_INPUT'), never a raw status number. `request_id`
    threads from `g.request_id` when a before_request set it, else 'unknown'.
    """
    return jsonify({
        'success': False,
        'error': message,
        'code': code,
        'request_id': g.get('request_id', 'unknown'),
    }), status
