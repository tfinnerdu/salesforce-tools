import time

from flask import Blueprint, jsonify

from config import Config
from db import db_available

_start_time = time.time()

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    uptime = time.time() - _start_time
    db_ok = db_available()
    status = 'ok' if db_ok else 'degraded'
    return jsonify({
        'status': status,
        'service': 'sf-mission-control',
        'version': Config.VERSION,
        'uptime_seconds': round(uptime, 2),
        'db_status': 'ok' if db_ok else 'unavailable',
    }), 200
