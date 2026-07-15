"""Dashboard Blueprint — Mission Control home page.

HTML page stays unversioned at the existing prefix, per the Doane standard.
The one JSON route moved to dashboard_api_bp under /api/v1/dashboard; the old
/dashboard/summary path 308-redirects there (register_legacy_json_redirect
below) so existing MC.api('/dashboard/summary') calls keep working unmodified.
"""
import logging

from flask import Blueprint, render_template, session

from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')
dashboard_api_bp = Blueprint('dashboard_api', __name__, url_prefix='/api/v1/dashboard')


@dashboard_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


# ── Page routes ───────────────────────────────────────────────────────────────

@dashboard_bp.route('/')
@dashboard_bp.route('')
def index():
    return render_template('dashboard/index.html')


register_legacy_json_redirect(dashboard_bp, '/api/v1/dashboard')


# ── API routes ────────────────────────────────────────────────────────────────

@dashboard_api_bp.route('/summary')
def api_summary():
    """Quick stats for the dashboard title bar — doesn't call SF, just reads DB."""
    org = session.get('active_org', 'dev')
    from db import get_cursor, db_available
    from config import Config
    summary = {
        'org': org,
        'mock': Config.SHOW_MOCK,
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
        except Exception as exc:
            logger.exception('dashboard summary query failed')
            return error_response(str(exc), 'SUMMARY_FAILED', 500)
    return ok(summary)
