"""Shared API response helpers.

Introduced with the CLI tab as the standards-conformant error envelope
(`{error, code, request_id}`), kept a superset of this app's existing
`{success, data}` / `{success:false, error}` envelope so the front-end
`MC.api` unwrapper keeps working unchanged. Now adopted app-wide alongside
the `/api/v1/` route versioning (see `register_legacy_json_redirect` below).
"""
import uuid

from flask import g, jsonify, redirect, request


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


_LEGACY_REDIRECT_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')


def register_legacy_json_redirect(blueprint, new_prefix: str) -> None:
    """Attach a catch-all 308 redirect from a blueprint's pre-versioning JSON
    paths to their new home under `new_prefix` (e.g. '/api/v1/cli').

    308 (not 301/302) preserves method + body, so POST-bearing calls survive
    the hop — this is what lets old frontend fetch() calls and CLI/Argo
    scripts keep working unmodified during the transition window the
    standard calls for, without a rewrite of every call site.

    Only matches non-empty subpaths (`/<prefix>/<subpath>`), never the bare
    `/<prefix>` or `/<prefix>/` root — those stay reserved for the
    blueprint's own HTML page route. Werkzeug always matches a static rule
    (e.g. an explicit `/objects` route) ahead of this `<path:...>` wildcard
    regardless of registration order, so an old JSON path can't be shadowed
    by adding this after the blueprint's other routes are already defined.
    """
    def _redirect(subpath):
        target = f'{new_prefix}/{subpath}'
        qs = request.query_string.decode()
        if qs:
            target = f'{target}?{qs}'
        return redirect(target, code=308)

    blueprint.add_url_rule(
        '/<path:subpath>',
        endpoint='_legacy_json_redirect',
        view_func=_redirect,
        methods=list(_LEGACY_REDIRECT_METHODS),
    )
