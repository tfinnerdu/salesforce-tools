import logging
from datetime import datetime, timezone, timedelta

from config import Config
from db import get_cursor, db_available

logger = logging.getLogger(__name__)

# Mock universe size — used only when SHOW_MOCK is on, so the velocity demo
# shows a plausible %-complete and ETA against a known total.
TOTAL_RECORDS_TARGET = 4312


def get_velocity_data(org: str, days: int = 30) -> dict:
    """
    Compute daily migration velocity from batch_tracker data.
    Returns: daily_counts (list of {date, records_processed}),
             cumulative (list of {date, total}),
             velocity_avg (records/day over last 7 days),
             eta_date (projected completion date string or None),
             total_migrated (int),
             target (int),
             pct_complete (float)
    """
    if Config.SHOW_MOCK:
        return _mock_velocity(days)

    batches = _get_batches_from_db(org)
    if not batches:
        return _empty_velocity(days)

    # Group by date
    from collections import defaultdict
    daily = defaultdict(int)
    for b in batches:
        ts = b.get('started_at') or b.get('created_at', '')
        if ts:
            try:
                date_str = str(ts)[:10]
                daily[date_str] += int(b.get('records_processed', 0) or 0)
            except Exception:
                pass

    # Fill gaps for last `days` days
    today = datetime.now(timezone.utc).date()
    result_daily = []
    cumulative = 0
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        ds = d.isoformat()
        count = daily.get(ds, 0)
        cumulative += count
        result_daily.append({'date': ds, 'records': count, 'cumulative': cumulative})

    total_migrated = cumulative
    target = Config.MIGRATION_RECORD_TARGET
    pct_complete = round(min(total_migrated / target * 100, 100), 1) if target else 0

    # Velocity: average over last 7 days with data
    recent = [d['records'] for d in result_daily[-7:] if d['records'] > 0]
    velocity_avg = round(sum(recent) / len(recent), 1) if recent else 0

    # ETA
    eta_date = None
    remaining = max(target - total_migrated, 0)
    if velocity_avg > 0 and remaining > 0:
        days_left = remaining / velocity_avg
        eta_dt = datetime.now(timezone.utc) + timedelta(days=days_left)
        eta_date = eta_dt.strftime('%Y-%m-%d')

    return {
        'daily': result_daily,
        'velocity_avg': velocity_avg,
        'eta_date': eta_date,
        'total_migrated': total_migrated,
        'target': target,
        'pct_complete': pct_complete,
    }


def list_recent_batches(org: str, limit: int = 20) -> list:
    """Return the most recent migration batches for the dashboard widget.

    A row in the migration_batches table represents a completed batch load.
    Returns [] when the DB is unavailable — the dashboard widget degrades
    gracefully to its 'No batch data' state.
    """
    batches = _get_batches_from_db(org)
    out = []
    for b in batches[:limit]:
        ts = b.get('started_at') or b.get('created_at') or ''
        out.append({
            'date': str(ts)[:19] if ts else '',
            'records': int(b.get('records_processed', 0) or 0),
            'status': 'Completed',
        })
    return out


def _get_batches_from_db(org: str) -> list:
    """Attempt to read batch records from DB. Returns empty list if DB unavailable."""
    if not db_available():
        return []
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT started_at, created_at, records_processed
                FROM migration_batches
                WHERE org = %s
                ORDER BY started_at DESC
                LIMIT 1000
                """,
                (org,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
    except Exception:
        logger.debug('migration_batches table not available, returning empty list')
        return []


def _empty_velocity(days: int = 30) -> dict:
    """Zeroed velocity payload for when no batch data exists yet.

    Keeps the response shape stable so the velocity view renders its empty
    state instead of erroring.
    """
    today = datetime.now(timezone.utc).date()
    daily = [
        {'date': (today - timedelta(days=i)).isoformat(), 'records': 0, 'cumulative': 0}
        for i in range(days, -1, -1)
    ]
    return {
        'daily': daily,
        'velocity_avg': 0,
        'eta_date': None,
        'total_migrated': 0,
        'target': Config.MIGRATION_RECORD_TARGET,
        'pct_complete': 0.0,
    }


def _mock_velocity(days: int = 30) -> dict:
    """Synthetic velocity payload for SHOW_MOCK demos."""
    today = datetime.now(timezone.utc).date()
    import random
    random.seed(42)
    daily = []
    cumulative = 0
    target = TOTAL_RECORDS_TARGET
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        records = random.randint(80, 160) if i > 5 else random.randint(20, 60)
        cumulative = min(cumulative + records, target)
        daily.append({'date': d.isoformat(), 'records': records, 'cumulative': cumulative})
    total_migrated = daily[-1]['cumulative']
    remaining = target - total_migrated
    velocity_avg = round(sum(d['records'] for d in daily[-7:]) / 7, 1)
    eta_date = None
    if velocity_avg > 0 and remaining > 0:
        eta_dt = datetime.now(timezone.utc) + timedelta(days=remaining / velocity_avg)
        eta_date = eta_dt.strftime('%Y-%m-%d')
    return {
        'daily': daily,
        'velocity_avg': velocity_avg,
        'eta_date': eta_date,
        'total_migrated': total_migrated,
        'target': target,
        'pct_complete': round(total_migrated / target * 100, 1),
    }
