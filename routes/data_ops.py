import logging

from flask import Blueprint, jsonify, redirect, render_template, request, Response, session, url_for

from services import join_builder, bulk_dml

logger = logging.getLogger(__name__)

data_ops_bp = Blueprint('data_ops', __name__, url_prefix='/data-ops')


# ── Page routes ───────────────────────────────────────────────────────────────

@data_ops_bp.route('/')
@data_ops_bp.route('')
def index():
    return redirect(url_for('data_ops.import_page'))


@data_ops_bp.route('/join')
def join():
    return render_template('data_ops/join_builder.html')


@data_ops_bp.route('/import')
def import_page():
    return render_template('data_ops/import.html')


@data_ops_bp.route('/delete')
def delete_page():
    return render_template('data_ops/delete.html')


@data_ops_bp.route('/modify')
def modify_page():
    return render_template('data_ops/modify.html')


@data_ops_bp.route('/reassign')
def reassign_page():
    return render_template('data_ops/reassign.html')


@data_ops_bp.route('/export')
def export_page():
    return render_template('data_ops/export.html')


@data_ops_bp.route('/tune')
def tune_page():
    return render_template('data_ops/tune.html')


@data_ops_bp.route('/match')
def match_page():
    return render_template('data_ops/match.html')


@data_ops_bp.route('/convert')
def convert_page():
    # Intentional stub — see templates/data_ops/convert.html for the rationale.
    return render_template('data_ops/convert.html')


@data_ops_bp.route('/bulk-update')
def bulk_update_page():
    return render_template('data_ops/bulk_update.html')


@data_ops_bp.route('/record-locks')
def record_locks_page():
    return render_template('data_ops/record_locks.html')


@data_ops_bp.route('/bulk-jobs')
def bulk_jobs_page():
    return render_template('data_ops/bulk_jobs.html')


# ── Import API ────────────────────────────────────────────────────────────────

@data_ops_bp.route('/import/fields', methods=['POST'])
def api_import_fields():
    """Return SF object fields for mapping UI."""
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    if not object_name:
        return jsonify({'success': False, 'error': 'object required'}), 400
    try:
        from services import data_importer
        fields = data_importer.get_object_fields(org, object_name)
        return jsonify({'success': True, 'data': fields})
    except Exception as exc:
        logger.exception('import fields failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/import/validate', methods=['POST'])
def api_import_validate():
    """Validate CSV rows against SF schema — no writes."""
    org = session.get('active_org', 'dev')
    body = request.form
    csv_file = request.files.get('csv_file')
    object_name = body.get('object', '').strip()
    operation = body.get('operation', 'insert').strip()
    import json
    field_mapping = json.loads(body.get('field_mapping', '{}'))

    if not csv_file or not object_name:
        return jsonify({'success': False, 'error': 'csv_file and object are required'}), 400
    try:
        csv_text = csv_file.read().decode('utf-8-sig')
        from services import data_importer
        result = data_importer.validate_csv(org, object_name, csv_text, field_mapping, operation)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('import validate failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/import/execute', methods=['POST'])
def api_import_execute():
    """Execute CSV import via Bulk API."""
    org = session.get('active_org', 'dev')
    body = request.form
    csv_file = request.files.get('csv_file')
    object_name = body.get('object', '').strip()
    operation = body.get('operation', 'insert').strip()
    external_id_field = body.get('external_id_field', '').strip()
    bypass_triggers = body.get('bypass_triggers', 'false').lower() == 'true'
    import json
    field_mapping = json.loads(body.get('field_mapping', '{}'))

    if not csv_file or not object_name:
        return jsonify({'success': False, 'error': 'csv_file and object are required'}), 400
    try:
        csv_text = csv_file.read().decode('utf-8-sig')
        from services import data_importer
        result = data_importer.import_csv(
            org, object_name, csv_text, field_mapping,
            operation, external_id_field, bypass_triggers,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('import execute failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/import/download-errors', methods=['POST'])
def api_import_download_errors():
    """Return error CSV as a file download."""
    error_csv = request.form.get('error_csv', '')
    filename = request.form.get('filename', 'import_errors.csv')
    return Response(
        error_csv,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ── Delete API ────────────────────────────────────────────────────────────────

@data_ops_bp.route('/delete/preview', methods=['POST'])
def api_delete_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not object_name or not where_clause:
        return jsonify({'success': False, 'error': 'object and where_clause required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_delete_preview(org, object_name, where_clause)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('delete preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/delete/execute', methods=['POST'])
def api_delete_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause:
        return jsonify({'success': False, 'error': 'object and where_clause required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_delete_execute(org, object_name, where_clause, bypass_triggers)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('delete execute failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Modify API ────────────────────────────────────────────────────────────────

@data_ops_bp.route('/modify/preview', methods=['POST'])
def api_modify_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_name = body.get('field', '').strip()
    new_value = body.get('value', '')
    if not object_name or not where_clause or not field_name:
        return jsonify({'success': False, 'error': 'object, where_clause, and field required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_modify_preview(org, object_name, where_clause, field_name, new_value)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('modify preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/modify/execute', methods=['POST'])
def api_modify_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_updates = body.get('field_updates', {})
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not field_updates:
        return jsonify({'success': False, 'error': 'object, where_clause, and field_updates required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_modify_execute(org, object_name, where_clause, field_updates, bypass_triggers)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('modify execute failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Reassign API ──────────────────────────────────────────────────────────────

@data_ops_bp.route('/reassign/users')
def api_reassign_users():
    org = session.get('active_org', 'dev')
    q = request.args.get('q', '').strip()
    try:
        from services import bulk_ops
        data = bulk_ops.search_users(org, q)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('reassign user search failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/reassign/preview', methods=['POST'])
def api_reassign_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not object_name or not where_clause:
        return jsonify({'success': False, 'error': 'object and where_clause required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_reassign_preview(org, object_name, where_clause)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('reassign preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/reassign/execute', methods=['POST'])
def api_reassign_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    new_owner_id = body.get('new_owner_id', '').strip()
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not new_owner_id:
        return jsonify({'success': False, 'error': 'object, where_clause, and new_owner_id required'}), 400
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_reassign_execute(org, object_name, where_clause, new_owner_id, bypass_triggers)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('reassign execute failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Export API ────────────────────────────────────────────────────────────────

@data_ops_bp.route('/export/run', methods=['POST'])
def api_export_run():
    org = session.get('active_org', 'dev')
    # Accept both JSON (from fetch) and form (from direct form submit)
    if request.content_type and 'application/json' in request.content_type:
        body = request.get_json(silent=True) or {}
    else:
        body = request.form
    soql = (body.get('soql', '') or '').strip()
    filename = (body.get('filename', 'export.csv') or 'export.csv').strip()
    all_pages_raw = body.get('all_pages', 'true')
    all_pages = str(all_pages_raw).lower() not in ('false', '0', '')
    if not soql:
        return jsonify({'success': False, 'error': 'soql required'}), 400
    try:
        from services import bulk_ops
        csv_text = bulk_ops.export_to_csv(org, soql, all_pages=all_pages)
        return Response(
            csv_text,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.exception('export failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── SQL Server schema cache (Join Builder) ────────────────────────────────────

@data_ops_bp.route('/sql-schema')
def api_sql_schema():
    """Cached SQL Server schema. ?table=<name> returns that table's columns;
    otherwise returns the table-name list + cache metadata."""
    table = request.args.get('table', '').strip()
    try:
        from services import sql_schema
        if table:
            return jsonify({'success': True, 'data': {
                'table': table,
                'columns': sql_schema.get_table_columns(table),
            }})
        cached = sql_schema.get_cached_schema()
        return jsonify({'success': True, 'data': {
            'captured_at': cached.get('captured_at'),
            'table_count': cached.get('table_count', 0),
            'mock': cached.get('mock', False),
            'tables': sorted(cached.get('tables', {}).keys()),
        }})
    except Exception as exc:
        logger.exception('sql schema read failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/sql-schema/refresh', methods=['POST'])
def api_sql_schema_refresh():
    """Re-introspect the SQL Server schema and cache it."""
    try:
        from services import sql_schema
        result = sql_schema.refresh_schema()
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('sql schema refresh failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/sf-objects')
def api_sf_objects():
    """All queryable Salesforce objects — for the Join Builder object picker."""
    org = session.get('active_org', 'dev')
    try:
        from services import soql_workbench
        objects = soql_workbench.list_objects(org)
        return jsonify({'success': True, 'data': objects})
    except Exception as exc:
        logger.exception('sf objects list failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/sf-object-fields')
def api_sf_object_fields():
    """Field list for one SF object — for the Join Builder field checker."""
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return jsonify({'success': False, 'error': 'object param required'}), 400
    try:
        from services import soql_workbench
        fields = soql_workbench.list_fields(org, object_name)
        return jsonify({'success': True, 'data': fields})
    except Exception as exc:
        logger.exception('sf object fields failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Tune (data standardization) API ───────────────────────────────────────────

@data_ops_bp.route('/tune/rules')
def api_tune_rules():
    try:
        from services import data_tuner
        return jsonify({'success': True, 'data': data_tuner.list_rules()})
    except Exception as exc:
        logger.exception('tune rules failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/tune/preview', methods=['POST'])
def api_tune_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_rules = body.get('field_rules', {})
    if not object_name or not where_clause or not field_rules:
        return jsonify({'success': False, 'error': 'object, where_clause, and field_rules required'}), 400
    try:
        from services import data_tuner
        result = data_tuner.preview_tune(org, object_name, where_clause, field_rules)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('tune preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@data_ops_bp.route('/tune/execute', methods=['POST'])
def api_tune_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_rules = body.get('field_rules', {})
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not field_rules:
        return jsonify({'success': False, 'error': 'object, where_clause, and field_rules required'}), 400
    try:
        from services import data_tuner
        result = data_tuner.apply_tune(org, object_name, where_clause, field_rules, bypass_triggers)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('tune execute failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Match (fuzzy duplicate detection) API ─────────────────────────────────────

@data_ops_bp.route('/match/run', methods=['POST'])
def api_match_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    compare_fields = body.get('compare_fields', [])
    block_field = body.get('block_field', '').strip()
    threshold = body.get('threshold', 0.85)
    if not object_name or not where_clause or not compare_fields or not block_field:
        return jsonify({'success': False,
                        'error': 'object, where_clause, compare_fields, and block_field required'}), 400
    try:
        from services import fuzzy_matcher
        result = fuzzy_matcher.find_matches(
            org, object_name, where_clause, compare_fields, block_field, threshold)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('match run failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


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

    # Accept _collectConfig() format from JS frontend:
    # {sql_table, sql_fields, join_field_sql, sf_object, sf_fields, join_field_sf}
    if not sql_query and body.get('sql_table'):
        built = join_builder.build_query(
            sql_table=body.get('sql_table', ''),
            sql_fields=body.get('sql_fields', []),
            sf_object=body.get('sf_object', ''),
            sf_fields=body.get('sf_fields', []),
            join_mapping={
                'sql_field': body.get('join_field_sql', ''),
                'sf_field': body.get('join_field_sf', ''),
            },
        )
        sql_query = built['sql_only']
        soql_query = built['soql']
        join_mapping = {
            'sql_field': built['join_field_sql'],
            'sf_field': built['join_field_sf'],
        }

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


@data_ops_bp.route('/bulk-update/preview', methods=['POST'])
def api_bulk_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not sobject or not where_clause:
        return jsonify({'success': False, 'data': None, 'error': 'sobject and where_clause required'}), 400
    try:
        result = bulk_dml.preview(org=org, sobject=sobject, where_clause=where_clause)
        return jsonify({'success': True, 'data': result})
    except Exception as exc:
        logger.exception('bulk preview failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@data_ops_bp.route('/bulk-update/execute', methods=['POST'])
def api_bulk_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field = body.get('field', '').strip()
    value = body.get('value')
    dry_run = bool(body.get('dry_run', True))
    if not sobject or not where_clause or not field:
        return jsonify({'success': False, 'data': None, 'error': 'sobject, where_clause, and field required'}), 400
    try:
        result = bulk_dml.bulk_update(org=org, sobject=sobject, where_clause=where_clause,
                                      field=field, value=value, dry_run=dry_run)
        return jsonify({'success': True, 'data': result})
    except ValueError as exc:
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('bulk execute failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@data_ops_bp.route('/api/record-locks')
def api_record_locks():
    org = session.get('active_org', 'dev')
    sobject = request.args.get('object', '')
    try:
        from services import record_lock_detector
        data = record_lock_detector.get_locked_records(org=org, sobject=sobject or None)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('record locks failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500


@data_ops_bp.route('/api/bulk-jobs')
def api_bulk_jobs():
    org = session.get('active_org', 'dev')
    try:
        limit = int(request.args.get('limit', 50))
        from services import bulk_job_history
        data = bulk_job_history.get_bulk_jobs(org=org, limit=limit)
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        logger.exception('bulk job history failed')
        return jsonify({'success': False, 'data': None, 'error': str(exc)}), 500
