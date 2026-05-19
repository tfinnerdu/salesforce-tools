"""Doane SF Mission Control — Flask application entry point."""
import logging
import os

from flask import Flask, redirect, url_for

from config import Config
from db import init_db
from routes.health import health_bp
from routes.migration import migration_bp
from routes.validation import validation_bp
from routes.soql import soql_bp
from routes.schema import schema_bp
from routes.data_ops import data_ops_bp
from routes.settings_routes import settings_bp
from routes.observe import observe_bp
from routes.logs import logs_bp
from routes.impact import impact_bp

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    app.register_blueprint(health_bp)
    app.register_blueprint(migration_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(soql_bp)
    app.register_blueprint(schema_bp)
    app.register_blueprint(data_ops_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(observe_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(impact_bp)

    @app.context_processor
    def inject_globals():
        from flask import session
        active_org = session.get('active_org', 'dev')
        return {
            'sf_mock_mode': Config.SF_MOCK,
            'sf_instance': session.get(f'sf_instance_{active_org}', ''),
        }

    @app.route('/')
    def root():
        return redirect(url_for('migration.index'))

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
