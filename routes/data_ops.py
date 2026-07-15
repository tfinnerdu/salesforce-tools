import logging

from flask import Blueprint, redirect, render_template, request, Response, session, url_for

from services import join_builder, bulk_dml
from utils.responses import error_response, new_request_id, ok, register_legacy_json_redirect

logger = logging.getLogger(__name__)

# HTML page(s) — stay unversioned at the existing prefix, per the Doane
# standard. JSON data/action routes (incl. the binary CSV/ZIP downloads, which
# are action routes that just happen to return non-JSON on success) moved to
# data_ops_api_bp under /api/v1/data-ops; the old /data-ops/<subpath> paths
# 308-redirect there (register_legacy_json_redirect below) so existing
# MC.api('/data-ops/...') calls keep working unmodified.
data_ops_bp = Blueprint('data_ops', __name__, url_prefix='/data-ops')
data_ops_api_bp = Blueprint('data_ops_api', __name__, url_prefix='/api/v1/data-ops')


@data_ops_api_bp.before_request
def _assign_request_id():
    from flask import g
    g.request_id = new_request_id()


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


@data_ops_bp.route('/backup')
def backup_page():
    return render_template('data_ops/backup.html')


@data_ops_bp.route('/bulk-update')
def bulk_update_page():
    return render_template('data_ops/bulk_update.html')


@data_ops_bp.route('/record-locks')
def record_locks_page():
    return render_template('data_ops/record_locks.html')


@data_ops_bp.route('/bulk-jobs')
def bulk_jobs_page():
    return render_template('data_ops/bulk_jobs.html')


@data_ops_bp.route('/file-migration')
def file_migration_page():
    return render_template('data_ops/file_migration.html')


register_legacy_json_redirect(data_ops_bp, '/api/v1/data-ops')


# ── Legacy path anomalies ─────────────────────────────────────────────────────
#
# Two old JSON routes had a redundant literal "api" segment baked into their
# path (/data-ops/api/record-locks, /data-ops/api/bulk-jobs) — a naming
# anomaly, not a versioning prefix. Their new canonical homes drop that
# redundant segment (/api/v1/data-ops/record-locks, /api/v1/data-ops/bulk-jobs)
# rather than becoming /api/v1/data-ops/api/... . The generic catch-all above
# does a blind 1:1 subpath copy, which would send these two to a path that
# doesn't exist, so they get explicit overrides here instead. Werkzeug always
# matches a literal rule ahead of the <path:subpath> catch-all regardless of
# registration order, so placement relative to the catch-all doesn't matter.

@data_ops_bp.route('/api/record-locks')
def _legacy_record_locks_redirect():
    target = '/api/v1/data-ops/record-locks'
    qs = request.query_string.decode()
    if qs:
        target = f'{target}?{qs}'
    return redirect(target, code=308)


@data_ops_bp.route('/api/bulk-jobs')
def _legacy_bulk_jobs_redirect():
    target = '/api/v1/data-ops/bulk-jobs'
    qs = request.query_string.decode()
    if qs:
        target = f'{target}?{qs}'
    return redirect(target, code=308)


# ── Import API ────────────────────────────────────────────────────────────────

@data_ops_api_bp.route('/import/fields', methods=['POST'])
def api_import_fields():
    """Return SF object fields for mapping UI."""
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    if not object_name:
        return error_response('object required', 'INVALID_INPUT', 400)
    try:
        from services import data_importer
        fields = data_importer.get_object_fields(org, object_name)
        return ok(fields)
    except Exception as exc:
        logger.exception('import fields failed')
        return error_response(str(exc), 'IMPORT_FIELDS_FAILED', 500)


@data_ops_api_bp.route('/import/validate', methods=['POST'])
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
        return error_response('csv_file and object are required', 'INVALID_INPUT', 400)
    try:
        csv_text = csv_file.read().decode('utf-8-sig')
        from services import data_importer
        result = data_importer.validate_csv(org, object_name, csv_text, field_mapping, operation)
        return ok(result)
    except Exception as exc:
        logger.exception('import validate failed')
        return error_response(str(exc), 'IMPORT_VALIDATE_FAILED', 500)


def _build_migration_cfg(body, files, tmp_paths):
    """Build a MigrationConfig from the multipart form for any remap method.

    Uploads / pasted lists are written to temp files (paths appended to
    tmp_paths for the caller to clean up) so the path-based engine is reused.
    Returns (cfg, error) where error is (message, status) or None.
    """
    import os
    import tempfile
    from services.file_migration import MigrationConfig, DEFAULT_MAX_MB

    try:
        max_mb = int(body.get('max_mb', DEFAULT_MAX_MB))
    except (TypeError, ValueError):
        max_mb = DEFAULT_MAX_MB
    mode = body.get('mode', 'files').strip()
    dest = body.get('dest', '').strip()
    remap = body.get('remap_method', 'crosswalk').strip()
    common = dict(
        max_mb=max_mb,
        mode=mode if mode in ('files', 'attachments') else 'files',
        dest=dest if dest in ('files', 'attachments') else '',
        remap=remap,
        share_type=body.get('share_type', 'V').strip() or 'V',
        visibility=body.get('visibility', 'AllUsers').strip() or 'AllUsers',
    )

    def _scope():
        """Scope by SOQL filter (where) or a pasted Id list (→ temp file)."""
        by = body.get('by', 'filter').strip()
        ids_file = ''
        if by == 'list':
            ids_text = body.get('ids', '').strip()
            if not ids_text:
                return None, ('a list of Ids / external-Id values is required', 400)
            fd, ids_file = tempfile.mkstemp(suffix='.txt')
            tmp_paths.append(ids_file)
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(ids_text)
        return dict(by=by, where=body.get('where', '').strip(), ids_file=ids_file), None

    if remap == 'ext_id':
        parent = body.get('parent', '').strip()
        ext_id = body.get('ext_id', '').strip()
        if not parent or not ext_id:
            return None, ('parent and ext_id are required for external-Id remap', 400)
        scope, err = _scope()
        if err:
            return None, err
        return MigrationConfig(parent=parent, ext_id=ext_id, **scope, **common), None

    if remap == 'identity':
        scope, err = _scope()
        if err:
            return None, err
        parent = body.get('parent', '').strip()
        if scope['by'] == 'filter' and not parent:
            return None, ('a parent object is required for a filter scope', 400)
        return MigrationConfig(parent=parent, **scope, **common), None

    # crosswalk (default)
    crosswalk = files.get('crosswalk_csv')
    if not crosswalk:
        return None, ('a crosswalk CSV is required', 400)
    fd, cw = tempfile.mkstemp(suffix='.csv')
    tmp_paths.append(cw)
    with os.fdopen(fd, 'wb') as fh:
        fh.write(crosswalk.read())
    return MigrationConfig(id_map=cw,
                           map_old_col=body.get('map_old_col', 'old_id').strip() or 'old_id',
                           map_new_col=body.get('map_new_col', 'new_id').strip() or 'new_id',
                           **common), None


def _run_file_migration(commit):
    """Shared handler for the file-migration plan (dry-run) / run (commit) routes."""
    import os
    from services import file_migration
    from sf_provider import get_sf

    body = request.form
    source = body.get('source', '').strip()
    target = body.get('target', '').strip()
    if not source or not target:
        return error_response('source and target are required', 'INVALID_INPUT', 400)

    tmp_paths = []
    try:
        cfg, err = _build_migration_cfg(body, request.files, tmp_paths)
        if err:
            return error_response(err[0], 'INVALID_INPUT', err[1])
        source_sf = get_sf(source)
        target_sf = get_sf(target)
        plan, resolved, unresolved, stats = file_migration.build_plan(source_sf, target_sf, cfg)
        summary = file_migration.summarize(plan, unresolved, cfg.max_mb)
        summary.update(stats)   # parents_in_scope / links_found / files_found
        data = {
            'summary': summary,
            'rows': file_migration.report_rows(plan)[:500],  # preview cap
            'committed': False,
        }
        if commit:
            data['counts'] = file_migration.execute(
                source_sf, target_sf, plan, cfg.mode, cfg.dest or cfg.mode,
                cfg.share_type, cfg.visibility)
            data['committed'] = True
        return ok(data)
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


@data_ops_api_bp.route('/file-migration/plan', methods=['POST'])
def api_file_migration_plan():
    """Dry-run the org-to-org file migration from an uploaded crosswalk — no writes."""
    try:
        return _run_file_migration(commit=False)
    except Exception as exc:
        logger.exception('file migration plan failed')
        return error_response(str(exc), 'FILE_MIGRATION_PLAN_FAILED', 500)


@data_ops_api_bp.route('/file-migration/run', methods=['POST'])
def api_file_migration_run():
    """Execute the org-to-org file migration (streams files, relinks parents)."""
    try:
        return _run_file_migration(commit=True)
    except Exception as exc:
        logger.exception('file migration run failed')
        return error_response(str(exc), 'FILE_MIGRATION_RUN_FAILED', 500)


@data_ops_api_bp.route('/import/execute', methods=['POST'])
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
        return error_response('csv_file and object are required', 'INVALID_INPUT', 400)
    try:
        csv_text = csv_file.read().decode('utf-8-sig')
        from services import data_importer
        result = data_importer.import_csv(
            org, object_name, csv_text, field_mapping,
            operation, external_id_field, bypass_triggers,
        )
        return ok(result)
    except Exception as exc:
        logger.exception('import execute failed')
        return error_response(str(exc), 'IMPORT_EXECUTE_FAILED', 500)


@data_ops_api_bp.route('/import/download-errors', methods=['POST'])
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

@data_ops_api_bp.route('/delete/preview', methods=['POST'])
def api_delete_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not object_name or not where_clause:
        return error_response('object and where_clause required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_delete_preview(org, object_name, where_clause)
        return ok(result)
    except Exception as exc:
        logger.exception('delete preview failed')
        return error_response(str(exc), 'DELETE_PREVIEW_FAILED', 500)


@data_ops_api_bp.route('/delete/execute', methods=['POST'])
def api_delete_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause:
        return error_response('object and where_clause required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_delete_execute(org, object_name, where_clause, bypass_triggers)
        return ok(result)
    except Exception as exc:
        logger.exception('delete execute failed')
        return error_response(str(exc), 'DELETE_EXECUTE_FAILED', 500)


# ── Modify API ────────────────────────────────────────────────────────────────

@data_ops_api_bp.route('/modify/preview', methods=['POST'])
def api_modify_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_name = body.get('field', '').strip()
    new_value = body.get('value', '')
    if not object_name or not where_clause or not field_name:
        return error_response('object, where_clause, and field required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_modify_preview(org, object_name, where_clause, field_name, new_value)
        return ok(result)
    except Exception as exc:
        logger.exception('modify preview failed')
        return error_response(str(exc), 'MODIFY_PREVIEW_FAILED', 500)


@data_ops_api_bp.route('/modify/execute', methods=['POST'])
def api_modify_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_updates = body.get('field_updates', {})
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not field_updates:
        return error_response('object, where_clause, and field_updates required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_modify_execute(org, object_name, where_clause, field_updates, bypass_triggers)
        return ok(result)
    except Exception as exc:
        logger.exception('modify execute failed')
        return error_response(str(exc), 'MODIFY_EXECUTE_FAILED', 500)


# ── Reassign API ──────────────────────────────────────────────────────────────

@data_ops_api_bp.route('/reassign/users')
def api_reassign_users():
    org = session.get('active_org', 'dev')
    q = request.args.get('q', '').strip()
    try:
        from services import bulk_ops
        data = bulk_ops.search_users(org, q)
        return ok(data)
    except Exception as exc:
        logger.exception('reassign user search failed')
        return error_response(str(exc), 'REASSIGN_USERS_FAILED', 500)


@data_ops_api_bp.route('/reassign/preview', methods=['POST'])
def api_reassign_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not object_name or not where_clause:
        return error_response('object and where_clause required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_reassign_preview(org, object_name, where_clause)
        return ok(result)
    except Exception as exc:
        logger.exception('reassign preview failed')
        return error_response(str(exc), 'REASSIGN_PREVIEW_FAILED', 500)


@data_ops_api_bp.route('/reassign/execute', methods=['POST'])
def api_reassign_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    new_owner_id = body.get('new_owner_id', '').strip()
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not new_owner_id:
        return error_response('object, where_clause, and new_owner_id required', 'INVALID_INPUT', 400)
    try:
        from services import bulk_ops
        result = bulk_ops.bulk_reassign_execute(org, object_name, where_clause, new_owner_id, bypass_triggers)
        return ok(result)
    except Exception as exc:
        logger.exception('reassign execute failed')
        return error_response(str(exc), 'REASSIGN_EXECUTE_FAILED', 500)


# ── Export API ────────────────────────────────────────────────────────────────

@data_ops_api_bp.route('/export/run', methods=['POST'])
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
        return error_response('soql required', 'INVALID_INPUT', 400)
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
        return error_response(str(exc), 'EXPORT_RUN_FAILED', 500)


# ── Data Backup API ───────────────────────────────────────────────────────────

@data_ops_api_bp.route('/backup/objects')
def api_backup_objects():
    from services import data_backup
    return ok(data_backup.DEFAULT_BACKUP_OBJECTS)


@data_ops_api_bp.route('/backup/run', methods=['POST'])
def api_backup_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    objects = body.get('objects') or None
    try:
        from services import data_backup
        result = data_backup.run_backup(org, objects, trigger='manual')
        return ok(result)
    except Exception as exc:
        logger.exception('backup run failed')
        return error_response(str(exc), 'BACKUP_RUN_FAILED', 500)


@data_ops_api_bp.route('/backup/list')
def api_backup_list():
    org = session.get('active_org', 'dev')
    try:
        from services import data_backup
        return ok(data_backup.list_backups(org))
    except Exception as exc:
        logger.exception('backup list failed')
        return error_response(str(exc), 'BACKUP_LIST_FAILED', 500)


@data_ops_api_bp.route('/backup/<int:run_id>/download')
def api_backup_download(run_id):
    try:
        from services import data_backup
        zip_bytes, filename = data_backup.build_archive(run_id)
        return Response(
            zip_bytes,
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        return error_response(str(exc), 'NOT_FOUND', 404)
    except Exception as exc:
        logger.exception('backup download failed')
        return error_response(str(exc), 'BACKUP_DOWNLOAD_FAILED', 500)


# ── SQL Server schema cache (Join Builder) ────────────────────────────────────

@data_ops_api_bp.route('/sql-schema')
def api_sql_schema():
    """Cached SQL Server schema. ?table=<name> returns that table's columns;
    otherwise returns the table-name list + cache metadata."""
    table = request.args.get('table', '').strip()
    try:
        from services import sql_schema
        if table:
            return ok({
                'table': table,
                'columns': sql_schema.get_table_columns(table),
            })
        cached = sql_schema.get_cached_schema()
        return ok({
            'captured_at': cached.get('captured_at'),
            'table_count': cached.get('table_count', 0),
            'mock': cached.get('mock', False),
            'tables': sorted(cached.get('tables', {}).keys()),
        })
    except Exception as exc:
        logger.exception('sql schema read failed')
        return error_response(str(exc), 'SQL_SCHEMA_FAILED', 500)


@data_ops_api_bp.route('/sql-schema/refresh', methods=['POST'])
def api_sql_schema_refresh():
    """Re-introspect the SQL Server schema and cache it."""
    try:
        from services import sql_schema
        result = sql_schema.refresh_schema()
        return ok(result)
    except Exception as exc:
        logger.exception('sql schema refresh failed')
        return error_response(str(exc), 'SQL_SCHEMA_REFRESH_FAILED', 500)


@data_ops_api_bp.route('/sf-object-fields')
def api_sf_object_fields():
    """Field list for one SF object — for the Join Builder field checker."""
    org = session.get('active_org', 'dev')
    object_name = request.args.get('object', '').strip()
    if not object_name:
        return error_response('object param required', 'INVALID_INPUT', 400)
    try:
        from services import soql_workbench
        fields = soql_workbench.list_fields(org, object_name)
        return ok(fields)
    except Exception as exc:
        logger.exception('sf object fields failed')
        return error_response(str(exc), 'SF_OBJECT_FIELDS_FAILED', 500)


# ── Tune (data standardization) API ───────────────────────────────────────────

@data_ops_api_bp.route('/tune/rules')
def api_tune_rules():
    try:
        from services import data_tuner
        return ok(data_tuner.list_rules())
    except Exception as exc:
        logger.exception('tune rules failed')
        return error_response(str(exc), 'TUNE_RULES_FAILED', 500)


@data_ops_api_bp.route('/tune/preview', methods=['POST'])
def api_tune_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_rules = body.get('field_rules', {})
    if not object_name or not where_clause or not field_rules:
        return error_response('object, where_clause, and field_rules required', 'INVALID_INPUT', 400)
    try:
        from services import data_tuner
        result = data_tuner.preview_tune(org, object_name, where_clause, field_rules)
        return ok(result)
    except Exception as exc:
        logger.exception('tune preview failed')
        return error_response(str(exc), 'TUNE_PREVIEW_FAILED', 500)


@data_ops_api_bp.route('/tune/execute', methods=['POST'])
def api_tune_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field_rules = body.get('field_rules', {})
    bypass_triggers = bool(body.get('bypass_triggers', False))
    if not object_name or not where_clause or not field_rules:
        return error_response('object, where_clause, and field_rules required', 'INVALID_INPUT', 400)
    try:
        from services import data_tuner
        result = data_tuner.apply_tune(org, object_name, where_clause, field_rules, bypass_triggers)
        return ok(result)
    except Exception as exc:
        logger.exception('tune execute failed')
        return error_response(str(exc), 'TUNE_EXECUTE_FAILED', 500)


# ── Match (fuzzy duplicate detection) API ─────────────────────────────────────

@data_ops_api_bp.route('/match/run', methods=['POST'])
def api_match_run():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    object_name = body.get('object', '').strip()
    where_clause = body.get('where_clause', '').strip()
    compare_fields = body.get('compare_fields', [])
    block_field = body.get('block_field', '').strip()
    threshold = body.get('threshold', 0.85)
    if not object_name or not where_clause or not compare_fields or not block_field:
        return error_response(
            'object, where_clause, compare_fields, and block_field required', 'INVALID_INPUT', 400)
    try:
        from services import fuzzy_matcher
        result = fuzzy_matcher.find_matches(
            org, object_name, where_clause, compare_fields, block_field, threshold)
        return ok(result)
    except Exception as exc:
        logger.exception('match run failed')
        return error_response(str(exc), 'MATCH_RUN_FAILED', 500)


# ── Join Builder API ──────────────────────────────────────────────────────────

@data_ops_api_bp.route('/join/build', methods=['POST'])
def api_join_build():
    body = request.get_json(silent=True) or {}
    sql_table = body.get('sql_table', '').strip()
    sql_fields = body.get('sql_fields', [])
    sf_object = body.get('sf_object', '').strip()
    sf_fields = body.get('sf_fields', [])
    join_mapping = body.get('join_mapping', {})
    if not sql_table or not sf_object:
        return error_response('sql_table and sf_object are required', 'INVALID_INPUT', 400)
    try:
        result = join_builder.build_query(
            sql_table=sql_table,
            sql_fields=sql_fields,
            sf_object=sf_object,
            sf_fields=sf_fields,
            join_mapping=join_mapping,
        )
        return ok(result)
    except Exception as exc:
        logger.exception('join build failed')
        return error_response(str(exc), 'JOIN_BUILD_FAILED', 500)


@data_ops_api_bp.route('/join/run', methods=['POST'])
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
        return error_response('sql_query and soql_query are required', 'INVALID_INPUT', 400)
    try:
        result = join_builder.run_join(
            org=org,
            sql_query=sql_query,
            soql_query=soql_query,
            join_mapping=join_mapping,
        )
        return ok(result)
    except Exception as exc:
        logger.exception('join run failed')
        return error_response(str(exc), 'JOIN_RUN_FAILED', 500)


@data_ops_api_bp.route('/bulk-update/preview', methods=['POST'])
def api_bulk_preview():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    where_clause = body.get('where_clause', '').strip()
    if not sobject or not where_clause:
        return error_response('sobject and where_clause required', 'INVALID_INPUT', 400)
    try:
        result = bulk_dml.preview(org=org, sobject=sobject, where_clause=where_clause)
        return ok(result)
    except Exception as exc:
        logger.exception('bulk preview failed')
        return error_response(str(exc), 'BULK_PREVIEW_FAILED', 500)


@data_ops_api_bp.route('/bulk-update/execute', methods=['POST'])
def api_bulk_execute():
    org = session.get('active_org', 'dev')
    body = request.get_json(silent=True) or {}
    sobject = body.get('sobject', '').strip()
    where_clause = body.get('where_clause', '').strip()
    field = body.get('field', '').strip()
    value = body.get('value')
    dry_run = bool(body.get('dry_run', True))
    if not sobject or not where_clause or not field:
        return error_response('sobject, where_clause, and field required', 'INVALID_INPUT', 400)
    try:
        result = bulk_dml.bulk_update(org=org, sobject=sobject, where_clause=where_clause,
                                      field=field, value=value, dry_run=dry_run)
        return ok(result)
    except ValueError as exc:
        return error_response(str(exc), 'BULK_EXECUTE_INVALID', 400)
    except Exception as exc:
        logger.exception('bulk execute failed')
        return error_response(str(exc), 'BULK_EXECUTE_FAILED', 500)


@data_ops_api_bp.route('/record-locks')
def api_record_locks():
    org = session.get('active_org', 'dev')
    sobject = request.args.get('object', '')
    try:
        from services import record_lock_detector
        data = record_lock_detector.get_locked_records(org=org, sobject=sobject or None)
        return ok(data)
    except Exception as exc:
        logger.exception('record locks failed')
        return error_response(str(exc), 'RECORD_LOCKS_FAILED', 500)


@data_ops_api_bp.route('/bulk-jobs')
def api_bulk_jobs():
    org = session.get('active_org', 'dev')
    try:
        from services import bulk_job_history
        data = bulk_job_history.get_bulk_jobs(org=org)
        return ok(data)
    except Exception as exc:
        logger.exception('bulk job history failed')
        return error_response(str(exc), 'BULK_JOBS_FAILED', 500)
