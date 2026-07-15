"""Doane SF Mission Control — Flask application entry point."""
import logging
import os

from flask import Flask, redirect, url_for
from flask_swagger_ui import get_swaggerui_blueprint

from config import Config
from db import init_db
from routes.health import health_bp
from routes.migration import migration_bp, migration_api_bp
from routes.validation import validation_bp, validation_api_bp
from routes.soql import soql_bp, soql_api_bp
from routes.schema import schema_bp, schema_api_bp
from routes.data_ops import data_ops_bp, data_ops_api_bp
from routes.settings_routes import settings_bp, settings_api_bp
from routes.observe import observe_bp, observe_api_bp
from routes.logs import logs_bp, logs_api_bp
from routes.impact import impact_bp, impact_api_bp
from routes.admin import admin_bp, admin_api_bp
from routes.deploy import deploy_bp, deploy_api_bp
from routes.dashboard import dashboard_bp, dashboard_api_bp
from routes.scenarios import scenarios_bp, scenarios_api_bp
from routes.key_map import key_map_bp, key_map_api_bp
from routes.cli import cli_bp, cli_api_bp
from routes.meta import meta_bp, meta_api_bp

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)

# Swagger UI for the app-wide /api/v1/ OpenAPI spec (static/openapi.yaml) —
# the last piece of the Doane API standard: a mounted, browsable contract for
# every JSON data/action route across all tabs.
SWAGGER_URL = '/swagger'
API_SPEC_URL = '/static/openapi.yaml'
swagger_ui_bp = get_swaggerui_blueprint(
    SWAGGER_URL, API_SPEC_URL,
    config={'app_name': 'SF Mission Control API'},
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    app.register_blueprint(health_bp)
    app.register_blueprint(migration_bp)
    app.register_blueprint(migration_api_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(validation_api_bp)
    app.register_blueprint(soql_bp)
    app.register_blueprint(soql_api_bp)
    app.register_blueprint(schema_bp)
    app.register_blueprint(schema_api_bp)
    app.register_blueprint(data_ops_bp)
    app.register_blueprint(data_ops_api_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(settings_api_bp)
    app.register_blueprint(observe_bp)
    app.register_blueprint(observe_api_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(logs_api_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(impact_api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_api_bp)
    app.register_blueprint(deploy_bp)
    app.register_blueprint(deploy_api_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(dashboard_api_bp)
    app.register_blueprint(scenarios_bp)
    app.register_blueprint(scenarios_api_bp)
    app.register_blueprint(key_map_bp)
    app.register_blueprint(key_map_api_bp)
    app.register_blueprint(cli_bp)
    app.register_blueprint(cli_api_bp)
    app.register_blueprint(meta_bp)
    app.register_blueprint(meta_api_bp)
    app.register_blueprint(swagger_ui_bp)

    @app.before_request
    def _ensure_active_org():
        from flask import session
        session.setdefault('active_org', Config.DEFAULT_ORG)

    @app.after_request
    def _mock_mode_header(response):
        # Third of the three required mock/live signals (navbar badge + this
        # header + the health/deep "mock" key) — lets a non-browser caller
        # (curl, a script, an Argo-triggered scheduled run) detect synthetic
        # data without parsing the response body.
        if Config.SHOW_MOCK:
            response.headers['X-Mock-Mode'] = 'true'
        return response

    @app.context_processor
    def inject_globals():
        from flask import session
        active_org = session.get('active_org', Config.DEFAULT_ORG)
        return {
            'show_mock_mode': Config.SHOW_MOCK,
            'sf_instance': session.get(f'sf_instance_{active_org}', ''),
            # Navbar picker shows the full explicit list (your environments);
            # the diff pickers use available_orgs() (configured subset).
            'nav_orgs': list(Config.AVAILABLE_ORGS),
        }

    @app.route('/')
    def root():
        return redirect(url_for('dashboard.index'))

    @app.route('/logout')
    def logout():
        from flask import session
        session.clear()
        return redirect(url_for('migration.index'))

    try:
        init_db()
        logger.info('"DB initialized"')
    except Exception:
        logger.warning('"DB init failed — running without persistent storage"')

    if Config.SCHEDULER_ENABLED:
        from scheduler import init_scheduler
        init_scheduler(app)
        logger.info('"APScheduler started"')

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.PORT, debug=False, use_reloader=False)
