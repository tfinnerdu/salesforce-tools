import csv
import io
import logging
from typing import Optional

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def parse_csv(content: str) -> list:
    """Parse CSV text into a list of mapping dicts; keep all rows."""
    reader = csv.DictReader(io.StringIO(content.strip()))
    rows = []
    for row in reader:
        rows.append({k.strip(): v.strip() for k, v in row.items()})
    return rows


def _count_populated(sf, obj: str, field: str) -> tuple:
    """Return (covered, total) for a field on an object."""
    try:
        total_res = sf.query(f"SELECT COUNT() FROM {obj}")
        total = total_res['totalSize']
        if total == 0:
            return 0, 0
        covered_res = sf.query(f"SELECT COUNT() FROM {obj} WHERE {field} != null")
        covered = covered_res['totalSize']
        return covered, total
    except Exception as exc:
        logger.error("crosswalk_diff._count_populated %s.%s: %s", obj, field, exc)
        return 0, 0


def run_live_check(org: str, mappings: list) -> list:
    """For each Mapped row, query both sides and compute coverage gap."""
    sf = get_sf(org)
    results = []

    for row in mappings:
        if row.get('status', '').strip() != 'Mapped':
            continue

        eda_obj = row.get('eda_object', '').strip()
        eda_field = row.get('eda_field', '').strip()
        ec_obj = row.get('ec_object', '').strip()
        ec_field = row.get('ec_field', '').strip()

        if not (eda_obj and eda_field and ec_obj and ec_field):
            continue

        # Query the EDA side
        eda_covered, eda_total = _count_populated(sf, eda_obj, eda_field)
        # Query the EC side
        ec_covered, ec_total = _count_populated(sf, ec_obj, ec_field)

        total = max(eda_total, ec_total, 1)

        eda_pct = round(100 * eda_covered / eda_total, 1) if eda_total else 0.0
        ec_pct = round(100 * ec_covered / ec_total, 1) if ec_total else 0.0
        gap = round(eda_pct - ec_pct, 1)

        if gap > 5:
            gap_direction = 'eda_ahead'
        elif gap < -5:
            gap_direction = 'ec_ahead'
        else:
            gap_direction = 'match'

        abs_gap = abs(gap)
        if gap_direction == 'match':
            row_status = 'match'
        elif abs_gap <= 20:
            row_status = 'warn'
        else:
            row_status = 'error'

        results.append({
            'eda_object': eda_obj,
            'eda_field': eda_field,
            'ec_object': ec_obj,
            'ec_field': ec_field,
            'eda_populated': eda_covered,
            'ec_populated': ec_covered,
            'total': total,
            'eda_pct': eda_pct,
            'ec_pct': ec_pct,
            'gap': gap,
            'gap_direction': gap_direction,
            'row_status': row_status,
        })

    return results
