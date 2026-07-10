"""Key Map blueprint — admin CRUD + preview/export for Source → SF key maps.

Page routes render the admin UI; API routes (under the same /key-maps prefix
per project convention) back it. Preview is read-only — it never writes to
Salesforce; it returns the would-be-inserted rows for review/export.
"""
import csv
import io
import logging

from flask import (Blueprint, Response, jsonify, render_template, request,
                   session)

from services import key_map as svc

logger = logging.getLogger(__name__)

key_map_bp = Blueprint('key_map', __name__, url_prefix='/key-maps')


# ── Page routes ──────────────────────────────────────────────────────────────

@key_map_bp.route('/')
@key_map_bp.route('')
def index():
    return render_template('key_map/index.html')


@key_map_bp.route('/new')
def new_page():
    return render_template('key_map/builder.html', key_map_id='new')


@key_map_bp.route('/<int:key_map_id>')
def builder_page(key_map_id):
    return render_template('key_map/builder.html', key_map_id=key_map_id)


@key_map_bp.route('/<int:key_map_id>/run')
def run_page(key_map_id):
    return render_template('key_map/run.html', key_map_id=key_map_id)


# ── Key map CRUD ─────────────────────────────────────────────────────────────

@key_map_bp.route('/list')
def api_list():
    try:
        return jsonify({'success': True, 'data': svc.list_key_maps()})
    except Exception as exc:
        logger.exception('key_map list failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/get/<int:key_map_id>')
def api_get(key_map_id):
    try:
        km = svc.get_key_map(key_map_id)
        if km is None:
            return jsonify({'success': False, 'error': 'Key map not found'}), 404
        return jsonify({'success': True, 'data': km})
    except Exception as exc:
        logger.exception('key_map get failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/create', methods=['POST'])
def api_create():
    body = request.get_json(silent=True) or {}
    try:
        km = svc.create_key_map(
            name=body.get('name', ''),
            description=body.get('description', ''),
            target_sobject=body.get('target_sobject', ''),
            created_by=session.get('user', 'system'),
        )
        return jsonify({'success': True, 'data': km}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('key_map create failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/update/<int:key_map_id>', methods=['POST'])
def api_update(key_map_id):
    body = request.get_json(silent=True) or {}
    try:
        km = svc.update_key_map(
            key_map_id, body.get('name', ''),
            body.get('description', ''), body.get('target_sobject', ''))
        if km is None:
            return jsonify({'success': False, 'error': 'Key map not found'}), 404
        return jsonify({'success': True, 'data': km})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('key_map update failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/<int:key_map_id>', methods=['DELETE'])
def api_delete(key_map_id):
    try:
        ok = svc.delete_key_map(key_map_id)
        if not ok:
            return jsonify({'success': False, 'error': 'Key map not found'}), 404
        return jsonify({'success': True, 'data': {'deleted': key_map_id}})
    except Exception as exc:
        logger.exception('key_map delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── FK lookups ───────────────────────────────────────────────────────────────

@key_map_bp.route('/<int:key_map_id>/fk-lookups', methods=['POST'])
def api_add_fk_lookup(key_map_id):
    body = request.get_json(silent=True) or {}
    try:
        row = svc.add_fk_lookup(
            key_map_id,
            source_column=body.get('source_column', ''),
            target_field=body.get('target_field', ''),
            lookup_sobject=body.get('lookup_sobject', ''),
            lookup_field=body.get('lookup_field', 'SIS_ID__c'),
            position=int(body.get('position', 0) or 0),
        )
        return jsonify({'success': True, 'data': row}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('fk lookup add failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/fk-lookups/<int:lookup_id>', methods=['DELETE'])
def api_delete_fk_lookup(lookup_id):
    try:
        ok = svc.delete_fk_lookup(lookup_id)
        return jsonify({'success': ok, 'data': {'deleted': lookup_id}})
    except Exception as exc:
        logger.exception('fk lookup delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Families + variants ──────────────────────────────────────────────────────

@key_map_bp.route('/<int:key_map_id>/families', methods=['POST'])
def api_add_family(key_map_id):
    body = request.get_json(silent=True) or {}
    try:
        row = svc.add_family(
            key_map_id,
            name=body.get('name', ''),
            routing=body.get('routing') or {},
            position=int(body.get('position', 0) or 0),
        )
        return jsonify({'success': True, 'data': row}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('family add failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/families/<int:family_id>', methods=['DELETE'])
def api_delete_family(family_id):
    try:
        ok = svc.delete_family(family_id)
        return jsonify({'success': ok, 'data': {'deleted': family_id}})
    except Exception as exc:
        logger.exception('family delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/families/<int:family_id>/variants', methods=['POST'])
def api_add_variant(family_id):
    body = request.get_json(silent=True) or {}
    try:
        row = svc.add_variant(
            family_id,
            name=body.get('name', ''),
            overlay=body.get('overlay') or {},
            applies_when=body.get('applies_when') or {},
            position=int(body.get('position', 0) or 0),
        )
        return jsonify({'success': True, 'data': row}), 201
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('variant add failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/variants/<int:variant_id>', methods=['DELETE'])
def api_delete_variant(variant_id):
    try:
        ok = svc.delete_variant(variant_id)
        return jsonify({'success': ok, 'data': {'deleted': variant_id}})
    except Exception as exc:
        logger.exception('variant delete failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


# ── Preview + export ─────────────────────────────────────────────────────────

_PREVIEW_SAMPLE = 200


@key_map_bp.route('/<int:key_map_id>/preview', methods=['POST'])
def api_preview(key_map_id):
    """Ingest a source spec, expand through the key map, and return the
    summary + a capped sample of output rows + the unresolved-FK list.

    Read-only — no Salesforce writes. The full result is persisted to
    key_map_runs so the export endpoint can stream every row.
    """
    body = request.get_json(silent=True) or {}
    source = body.get('source') or {}
    org = session.get('active_org', 'dev')
    try:
        from services import ingest
        rows = ingest.load_source_rows(source, org)
        result = svc.resolve_and_expand(key_map_id, rows, org)
        run_id = svc.save_run(key_map_id, org, result)
        out_rows = result['output_rows']
        return jsonify({'success': True, 'data': {
            'run_id': run_id,
            'summary': result['summary'],
            'unresolved_fks': result['unresolved_fks'][:_PREVIEW_SAMPLE],
            'unresolved_truncated': len(result['unresolved_fks']) > _PREVIEW_SAMPLE,
            'sample_rows': out_rows[:_PREVIEW_SAMPLE],
            'sample_truncated': len(out_rows) > _PREVIEW_SAMPLE,
        }})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('key_map preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


@key_map_bp.route('/<int:key_map_id>/export', methods=['POST'])
def api_export(key_map_id):
    """Run the expansion and stream the full output as a CSV download."""
    body = request.get_json(silent=True) or request.form or {}
    if not body:
        import json as _json
        try:
            body = _json.loads(request.data or '{}')
        except Exception:
            body = {}
    source = body.get('source') or {}
    org = session.get('active_org', 'dev')
    try:
        from services import ingest
        rows = ingest.load_source_rows(source, org)
        result = svc.resolve_and_expand(key_map_id, rows, org)
        svc.save_run(key_map_id, org, result)
        out_rows = result['output_rows']
        csv_text = _rows_to_csv(out_rows)
        km = svc.get_key_map(key_map_id, include_children=False)
        name = (km or {}).get('name', f'key_map_{key_map_id}').replace(' ', '_')
        return Response(
            csv_text, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{name}_preview.csv"'},
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('key_map export failed')
        return jsonify({'success': False, 'error': str(exc)}), 500


def _rows_to_csv(rows: list) -> str:
    """Serialise output rows to CSV. Columns are the union of all keys, with
    the internal _source_row_idx / _family / _variant columns kept last for
    traceability."""
    if not rows:
        return ''
    meta = ['_family', '_variant', '_source_row_idx']
    data_cols = []
    for r in rows:
        for k in r:
            if k not in meta and k not in data_cols:
                data_cols.append(k)
    columns = data_cols + [m for m in meta if any(m in r for r in rows)]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()
