import time

from flask import Blueprint, jsonify, redirect, url_for

from config import Config
from db import db_available

_start_time = time.time()

health_bp = Blueprint('health', __name__)


def _uptime() -> float:
    return round(time.time() - _start_time, 2)


@health_bp.route('/health')
def health_legacy():
    """Deprecated bare path — redirects to the versioned liveness endpoint."""
    return redirect(url_for('health.health_liveness'), code=308)


@health_bp.route('/api/v1/health')
def health_liveness():
    """Liveness — polling-safe. No dependency calls; 200 as long as the
    process is alive. Never emits an audit event (health endpoints are exempt)."""
    return jsonify({
        'status': 'ok',
        'service': 'sf-mission-control',
        'version': Config.VERSION,
        'uptime_seconds': _uptime(),
    }), 200


@health_bp.route('/api/v1/health/deep')
def health_readiness():
    """Readiness — real dependency probes, for CI gates and admin-triggered
    diagnostics, not automated polling.

    Postgres is treated as a non-critical dependency for THIS app on purpose:
    app.py's create_app() explicitly tolerates init_db() failing ("running
    without persistent storage") because most tabs (SOQL, Schema, Migration
    reporting, Data Ops DML) don't touch Postgres at all — only Scenarios,
    Key Maps, saved queries, and audit persistence do. With a single replica
    and no leader election in scheduler.py, hard-failing readiness (503) on a
    DB blip would take the whole app offline for a partial-feature outage, so
    a DB outage reports 200 with status 'degraded' rather than 503. Revisit
    this if/when the app runs multiple replicas.
    """
    start = time.time()
    db_ok = db_available()
    db_latency_ms = round((time.time() - start) * 1000, 1)
    return jsonify({
        'status': 'ok' if db_ok else 'degraded',
        'service': 'sf-mission-control',
        'version': Config.VERSION,
        'uptime_seconds': _uptime(),
        'mock': Config.SHOW_MOCK,
        'checks': {
            'database': {
                'status': 'ok' if db_ok else 'unavailable',
                'latency_ms': db_latency_ms,
            },
        },
    }), 200
