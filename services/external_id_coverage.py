import logging
from typing import Optional

from sf_provider import get_sf

logger = logging.getLogger(__name__)

TRACKED_OBJECTS = [
    ('Account', 'IsPersonAccount = true', ['SIS_ID__c', 'Ethos_Guid__c']),
    ('ContactPointEmail', None, ['SIS_ID__c']),
    ('ContactPointPhone', None, ['SIS_ID__c']),
    ('ContactPointAddress', None, ['SIS_ID__c']),
    ('IndividualApplication', None, ['SIS_ID__c', 'Ethos_Guid__c']),
]


def _field_status(pct: float) -> str:
    if pct >= 100:
        return 'green'
    if pct >= 90:
        return 'amber'
    return 'red'


def _build_where(base_filter: Optional[str], extra: Optional[str] = None) -> str:
    """Combine an optional base filter with an optional extra clause."""
    parts = [p for p in [base_filter, extra] if p]
    return ' AND '.join(parts) if parts else ''


def run(org: str) -> list:
    """Return external ID coverage stats for all tracked objects."""
    sf = get_sf(org)
    results = []

    for obj, base_filter, fields in TRACKED_OBJECTS:
        where_base = _build_where(base_filter)
        where_clause = f"WHERE {where_base}" if where_base else ''

        total_res = sf.query(f"SELECT COUNT() FROM {obj} {where_clause}".strip())
        total = total_res['totalSize']

        field_stats = {}
        for field in fields:
            covered_where = _build_where(base_filter, f'{field} != null')
            covered_clause = f"WHERE {covered_where}" if covered_where else ''
            covered_res = sf.query(
                f"SELECT COUNT() FROM {obj} {covered_clause}".strip()
            )
            covered = covered_res['totalSize']
            pct = round(100 * covered / total, 2) if total else 0.0
            field_stats[field] = {
                'covered': covered,
                'total': total,
                'pct': pct,
                'status': _field_status(pct),
            }

        results.append({
            'object': obj,
            'total': total,
            'fields': field_stats,
        })

    return results


def get_missing_records(
    org: str,
    obj: str,
    where_clause: Optional[str],
    field: str,
    limit: int = 200,
) -> list:
    """Return up to `limit` records where the given field is null."""
    sf = get_sf(org)
    base_filter = f"{where_clause} AND " if where_clause else ''
    soql = (
        f"SELECT Id, Name FROM {obj} "
        f"WHERE {base_filter}{field} = null "
        f"LIMIT {limit}"
    )
    result = sf.query(soql)
    records = result.get('records', [])
    return [{k: v for k, v in r.items() if k != 'attributes'} for r in records]
