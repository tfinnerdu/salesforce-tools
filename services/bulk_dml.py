"""Bulk DML service — preview and update a single field across a SOQL-matched record set."""
import logging

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

MAX_RECORDS = 10_000  # hard cap per operation


def preview(org: str, sobject: str, where_clause: str) -> dict:
    """Return count + sample IDs for records matching the WHERE clause.

    Returns:
        {sobject, where_clause, count, sample_ids, exceeds_limit}
    """
    try:
        sf = get_sf(org)
        count_soql = f"SELECT COUNT() FROM {sobject} WHERE {where_clause}"
        count_result = sf.query(count_soql)
        count = count_result.get('totalSize', 0)

        sample_soql = f"SELECT Id FROM {sobject} WHERE {where_clause} LIMIT 5"
        sample_result = sf.query(sample_soql)
        sample_ids = [r['Id'] for r in sample_result.get('records', [])]

        return {
            'sobject': sobject,
            'where_clause': where_clause,
            'count': count,
            'sample_ids': sample_ids,
            'exceeds_limit': count > MAX_RECORDS,
        }
    except Exception as exc:
        logger.exception('preview failed for %s WHERE %s', sobject, where_clause)
        raise RuntimeError(f'Preview failed: {exc}') from exc


def bulk_update(org: str, sobject: str, where_clause: str,
                field: str, value, dry_run: bool = True) -> dict:
    """Update field=value on all records matching where_clause.

    Returns:
        {status, records_queried, records_updated, records_failed, dry_run, errors}

    Raises:
        ValueError: if records_queried > MAX_RECORDS
    """
    try:
        prev = preview(org=org, sobject=sobject, where_clause=where_clause)
        count = prev['count']

        if count > MAX_RECORDS:
            raise ValueError(
                f"Operation aborted: {count:,} records match WHERE clause, "
                f"exceeding the {MAX_RECORDS:,}-record cap. "
                "Narrow your WHERE clause and try again."
            )

        if dry_run:
            return {
                'status': 'dry_run',
                'records_queried': count,
                'records_updated': 0,
                'records_failed': 0,
                'dry_run': True,
                'errors': [],
            }

        # Real execution path
        sf = get_sf(org)
        id_soql = f"SELECT Id FROM {sobject} WHERE {where_clause} LIMIT {MAX_RECORDS}"
        id_result = sf.query(id_soql)
        records = id_result.get('records', [])
        update_list = [{'Id': r['Id'], field: value} for r in records]

        if Config.SF_MOCK:
            # Mock mode — simulate a successful bulk update
            return {
                'status': 'ok',
                'records_queried': len(update_list),
                'records_updated': len(update_list),
                'records_failed': 0,
                'dry_run': False,
                'errors': [],
            }

        # Real bulk API call
        bulk_obj = getattr(sf.bulk, sobject)
        results = bulk_obj.update(update_list)

        records_updated = 0
        records_failed = 0
        errors = []
        for item in results:
            if item.get('success'):
                records_updated += 1
            else:
                records_failed += 1
                errors.append({
                    'id': item.get('id', ''),
                    'error': '; '.join(
                        e.get('message', str(e)) for e in item.get('errors', [])
                    ),
                })

        status = 'ok' if records_failed == 0 else ('partial' if records_updated > 0 else 'error')
        return {
            'status': status,
            'records_queried': len(update_list),
            'records_updated': records_updated,
            'records_failed': records_failed,
            'dry_run': False,
            'errors': errors,
        }

    except ValueError:
        raise
    except Exception as exc:
        logger.exception('bulk_update failed for %s.%s WHERE %s', sobject, field, where_clause)
        raise RuntimeError(f'Bulk update failed: {exc}') from exc
