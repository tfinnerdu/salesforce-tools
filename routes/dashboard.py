"""Dashboard Blueprint — Mission Control home page."""
import logging

from flask import Blueprint, jsonify, render_template, session

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


# ── Page routes ───────────────────────────────────────────────────────────────

@dashboard_bp.route('/')
@dashboard_bp.route('')
def index():
    return render_template('dashboard/index.html')


# ── API routes ────────────────────────────────────────────────────────────────

@dashboard_bp.route('/summary')
def api_summary():
    """Quick stats for the dashboard title bar — doesn't call SF, just reads DB."""
    org = session.get('active_org', 'dev')
    from db import get_cursor, db_available
    summary = {
        'org': org,
        'readiness_pct': None,
        'preflight_pct': None,
    }
    if db_available():
        try:
            with get_cursor() as cur:
                # latest readiness run
                cur.execute(
                    "SELECT overall_pct FROM readiness_runs WHERE org=%s ORDER BY run_at DESC LIMIT 1",
                    (org,)
                )
                row = cur.fetchone()
                if row:
                    summary['readiness_pct'] = round(row['overall_pct'], 1)
                # preflight progress
                cur.execute(
                    "SELECT COUNT(*) total, SUM(CASE WHEN checked THEN 1 ELSE 0 END) checked "
                    "FROM preflight_items WHERE org=%s",
                    (org,)
                )
                row = cur.fetchone()
                if row and row['total']:
                    summary['preflight_pct'] = round(row['checked'] / row['total'] * 100, 1)
        except Exception:
            pass
    return jsonify({'success': True, 'data': summary})
