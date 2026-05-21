"""Merge History service — records every Account merge from Duplicate Radar."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS merge_history (
    id          SERIAL PRIMARY KEY,
    org         VARCHAR(50)  NOT NULL,
    master_id   VARCHAR(20)  NOT NULL,
    victim_id   VARCHAR(20)  NOT NULL,
    merged_at   TIMESTAMP    DEFAULT NOW(),
    bypass_used BOOLEAN      DEFAULT FALSE,
    status      VARCHAR(20)  DEFAULT 'success',
    error_msg   TEXT
);
"""


def _ensure_table() -> None:
    """Create merge_history table if it does not exist. No-op when DB unavailable."""
    from db import get_cursor, db_available
    if not db_available():
        return
    with get_cursor() as cur:
        cur.execute(_ENSURE_SQL)


def log_merge(
    org: str,
    master_id: str,
    victim_id: str,
    bypass_used: bool = False,
    status: str = 'success',
    error_msg: Optional[str] = None,
) -> None:
    """Record a merge operation. Non-fatal — logs warning on failure."""
    try:
        from db import get_cursor, db_available
        if not db_available():
            logger.warning('log_merge: DB unavailable, skipping persistence')
            return
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO merge_history (org, master_id, victim_id, bypass_used, status, error_msg)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (org, master_id, victim_id, bypass_used, status, error_msg),
            )
    except Exception as exc:
        logger.warning('log_merge failed (non-fatal): %s', exc)


def list_merges(org: str, limit: int = 100) -> list:
    """Return recent merges for the org, newest first.

    Returns mock data only when SF_MOCK is enabled and DB is unavailable.
    Each item: {id, org, master_id, victim_id, merged_at, bypass_used, status, error_msg}
    """
    from config import Config
    try:
        from db import get_cursor, db_available
        if not db_available():
            return _mock_merges(org) if Config.SF_MOCK else []
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, org, master_id, victim_id,
                       merged_at, bypass_used, status, error_msg
                FROM merge_history
                WHERE org = %s
                ORDER BY merged_at DESC
                LIMIT %s
                """,
                (org, limit),
            )
            rows = cur.fetchall()
        if not rows:
            return _mock_merges(org) if Config.SF_MOCK else []
        return [
            {
                'id': r['id'],
                'org': r['org'],
                'master_id': r['master_id'],
                'victim_id': r['victim_id'],
                'merged_at': r['merged_at'].isoformat() if hasattr(r['merged_at'], 'isoformat') else str(r['merged_at']),
                'bypass_used': bool(r['bypass_used']),
                'status': r['status'],
                'error_msg': r['error_msg'],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning('list_merges failed: %s', exc)
        return _mock_merges(org) if Config.SF_MOCK else []


def _mock_merges(org: str) -> list:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return [
        {
            'id': 1,
            'org': org,
            'master_id': '001A000001abc001',
            'victim_id': '001A000001abc002',
            'merged_at': (now - timedelta(hours=1)).isoformat(),
            'bypass_used': False,
            'status': 'success',
            'error_msg': None,
        },
        {
            'id': 2,
            'org': org,
            'master_id': '001A000001abc003',
            'victim_id': '001A000001abc004',
            'merged_at': (now - timedelta(hours=3)).isoformat(),
            'bypass_used': True,
            'status': 'success',
            'error_msg': None,
        },
        {
            'id': 3,
            'org': org,
            'master_id': '001A000001abc005',
            'victim_id': '001A000001abc006',
            'merged_at': (now - timedelta(days=1)).isoformat(),
            'bypass_used': False,
            'status': 'error',
            'error_msg': 'Merge failed: insufficient privileges',
        },
    ]


def get_stats(org: str) -> dict:
    """Return {total_merges, successful, failed, bypass_used_count}."""
    from config import Config
    _empty = {'total_merges': 0, 'successful': 0, 'failed': 0, 'bypass_used_count': 0}
    try:
        from db import get_cursor, db_available
        if not db_available():
            return _mock_stats(org) if Config.SF_MOCK else _empty
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)                                   AS total_merges,
                    COUNT(*) FILTER (WHERE status = 'success') AS successful,
                    COUNT(*) FILTER (WHERE status = 'error')   AS failed,
                    COUNT(*) FILTER (WHERE bypass_used = TRUE)  AS bypass_used_count
                FROM merge_history
                WHERE org = %s
                """,
                (org,),
            )
            row = cur.fetchone()
        if not row or row['total_merges'] == 0:
            return _mock_stats(org) if Config.SF_MOCK else _empty
        return {
            'total_merges': int(row['total_merges']),
            'successful': int(row['successful']),
            'failed': int(row['failed']),
            'bypass_used_count': int(row['bypass_used_count']),
        }
    except Exception as exc:
        logger.warning('get_stats failed: %s', exc)
        return _mock_stats(org) if Config.SF_MOCK else _empty


def _mock_stats(org: str) -> dict:
    """Derive stats from mock merge list."""
    merges = _mock_merges(org)
    return {
        'total_merges': len(merges),
        'successful': sum(1 for m in merges if m['status'] == 'success'),
        'failed': sum(1 for m in merges if m['status'] == 'error'),
        'bypass_used_count': sum(1 for m in merges if m['bypass_used']),
    }
