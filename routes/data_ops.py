import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import join_builder

logger = logging.getLogger(__name__)

data_ops_bp = Blueprint('data_ops', __name__, url_prefix='/data-ops')


# ── Page routes ───────────────────────────────────────────────────────────────

@data_ops_bp.route('/')
@data_ops_bp.route('')
def index():
    return redirect(url_for('data_ops.join'))


@data_ops_bp.route('/join')
def join():
    return render_template('data_ops/join_builder.html')


# ── API routes ────────────────────────────────────────────────────────────────

@data_ops_bp.route('/join/build', methods=['POST'])
def api_join_build():
    body = request.get_json(silent=True) or {}
    sql_table = body.get('sql_table', '').strip()
    sql_fields = body.get('sql_fields', [])
    sf_object = body.get('sf_object', '').strip()
    sf_fields = body.get('sf_fields', [])
    join_mapping = body.get('join_mapping', {})
    if not sql_table or not sf_object:
        return jsonify({'success': False, 'data': None, 'error': 'sql_table and sf_object are required'}), 400
    try:
        result = join_builder.build_query(
            sql_table=sql_table,
            sql_fields=sql_fields,
            sf_object=sf_object,
            sf_fields=sf_fields,
            join_mapping=join_mapping,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('join build failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@data_ops_bp.route('/join/run', methods=['POST'])
def api_join_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sql_query = body.get('sql_query', '').strip()
    soql_query = body.get('soql_query', '').strip()
    join_mapping = body.get('join_mapping', {})
    if not sql_query or not soql_query:
        return jsonify({'success': False, 'data': None, 'error': 'sql_query and soql_query are required'}), 400
    try:
        result = join_builder.run_join(
            org=org,
            sql_query=sql_query,
            soql_query=soql_query,
            join_mapping=join_mapping,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('join run failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
