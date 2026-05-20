"""Pre-flight Go-Live Checklist service.

DB table (created on first use by _ensure_table()):

    CREATE TABLE IF NOT EXISTS preflight_items (
        id          SERIAL PRIMARY KEY,
        org         VARCHAR(50) NOT NULL DEFAULT 'dev',
        category    VARCHAR(100) NOT NULL,
        label       TEXT NOT NULL,
        description TEXT,
        checked     BOOLEAN NOT NULL DEFAULT FALSE,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        is_default  BOOLEAN NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMP DEFAULT NOW(),
        updated_at  TIMESTAMP DEFAULT NOW()
    );
"""
import logging

logger = logging.getLogger(__name__)

_ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS preflight_items (
    id          SERIAL PRIMARY KEY,
    org         VARCHAR(50) NOT NULL DEFAULT 'dev',
    category    VARCHAR(100) NOT NULL,
    label       TEXT NOT NULL,
    description TEXT,
    checked     BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_default  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
"""

# (category, label, description, sort_order)
DEFAULT_ITEMS = [
    ('Data Quality',    'SIS ID coverage ≥ 99%',             'Verify SIS_ID__c is populated on all Person Accounts. Run Field Completeness check.', 10),
    ('Data Quality',    'Ethos GUID coverage ≥ 99%',          'Verify Ethos_Guid__c is populated. Cross-check with LDM.', 20),
    ('Data Quality',    'Zero orphaned ContactPoints',         'Run Orphaned Record Scanner — all checks must show 0.', 30),
    ('Data Quality',    'Duplicate scan clean',               'Run Duplicate Radar — resolve all high-confidence duplicates.', 40),
    ('Data Quality',    'External ID coverage validated',     'Run External ID Coverage check — both SIS and Ethos IDs confirmed.', 50),
    ('Integrations',    'Conductor API connection verified',  'Settings → Test Conductor Connection → green.', 60),
    ('Integrations',    'All org connections tested',         'Settings → Test Connection for dev, sandbox, prod — all green.', 70),
    ('Integrations',    'Named Credentials confirmed',        'Admin → Integrations → Named Credentials — all endpoints correct.', 80),
    ('Integrations',    'Remote Site Settings active',        'Admin → Integrations → Remote Sites — all active.', 90),
    ('Permissions',     'Migration Admin perm set assigned',  'Confirm migration service account has Migration Admin permission set.', 100),
    ('Permissions',     'Bypass Triggers tested',             'Settings → Bypass Triggers toggle — verify it works in sandbox.', 110),
    ('Permissions',     'Sysadmin count reviewed',            'Admin → User Audit → confirm sysadmin count matches expected.', 120),
    ('Testing',         'Test coverage ≥ 75% on all Apex',   'Admin → Test Coverage → all classes green.', 130),
    ('Testing',         'Sandbox drift within tolerance',     'Observe → Sandbox Drift — all checks green vs prod baseline.', 140),
    ('Testing',         'Regression suite baseline set',      'Impact → Regression Tester — run suite and set baseline.', 150),
    ('Go-Live',         'Maintenance window confirmed',       'Confirm maintenance window with stakeholders and IT.', 160),
    ('Go-Live',         'Rollback plan documented',           'Document rollback steps in case of critical failure.', 170),
    ('Go-Live',         'Bypass triggers enabled for load',   'Enable bypass triggers before starting bulk migration load.', 180),
    ('Go-Live',         'Bulk load completed',                'All migration batches completed with 0 errors.', 190),
    ('Go-Live',         'Bypass triggers disabled after load','Disable bypass triggers after migration load finishes.', 200),
    ('Go-Live',         'Post-load validation run',          'Run full readiness check on prod — all checks green.', 210),
]


def _ensure_table() -> None:
    """Create the preflight_items table if it does not exist."""
    from db import get_cursor, db_available
    if not db_available():
        return
    with get_cursor() as cur:
        cur.execute(_ENSURE_SQL)


def seed_defaults(org: str) -> None:
    """Insert default items for an org if none exist yet."""
    from db import get_cursor, db_available
    if not db_available():
        return
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM preflight_items WHERE org = %s",
            (org,),
        )
        row = cur.fetchone()
        count = row['cnt'] if row else 0
        if count > 0:
            return
        for category, label, description, sort_order in DEFAULT_ITEMS:
            cur.execute(
                """
                INSERT INTO preflight_items (org, category, label, description, sort_order, is_default)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                """,
                (org, category, label, description, sort_order),
            )


def list_items(org: str) -> list:
    """Return all checklist items for org ordered by sort_order."""
    from db import get_cursor, db_available
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, org, category, label, description, checked, sort_order, is_default, created_at, updated_at
            FROM preflight_items
            WHERE org = %s
            ORDER BY sort_order, id
            """,
            (org,),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def toggle_item(org: str, item_id: int, checked: bool) -> dict:
    """Toggle checked state for an item. Returns updated item dict."""
    from db import get_cursor
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE preflight_items
            SET checked = %s, updated_at = NOW()
            WHERE id = %s AND org = %s
            RETURNING id, org, category, label, description, checked, sort_order, is_default, created_at, updated_at
            """,
            (checked, item_id, org),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Item {item_id} not found for org {org!r}")
    return dict(row)


def add_item(org: str, category: str, label: str, description: str = '') -> dict:
    """Add a custom checklist item. Returns the new item dict."""
    from db import get_cursor
    with get_cursor() as cur:
        # Place at the end of the list
        cur.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_order FROM preflight_items WHERE org = %s",
            (org,),
        )
        row = cur.fetchone()
        next_order = row['next_order'] if row else 10
        cur.execute(
            """
            INSERT INTO preflight_items (org, category, label, description, sort_order, is_default)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            RETURNING id, org, category, label, description, checked, sort_order, is_default, created_at, updated_at
            """,
            (org, category, label, description, next_order),
        )
        new_row = cur.fetchone()
    return dict(new_row)


def delete_item(org: str, item_id: int) -> bool:
    """Delete an item. Returns True if a row was deleted."""
    from db import get_cursor
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM preflight_items WHERE id = %s AND org = %s RETURNING id",
            (item_id, org),
        )
        deleted = cur.fetchone()
    return deleted is not None


def get_progress(org: str) -> dict:
    """Return {total, checked, pct, by_category: {cat: {total, checked}}}."""
    from db import get_cursor, db_available
    empty = {'total': 0, 'checked': 0, 'pct': 0, 'by_category': {}}
    if not db_available():
        return empty
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                category,
                COUNT(*) AS total,
                SUM(CASE WHEN checked THEN 1 ELSE 0 END) AS checked
            FROM preflight_items
            WHERE org = %s
            GROUP BY category
            ORDER BY MIN(sort_order)
            """,
            (org,),
        )
        rows = cur.fetchall()

    if not rows:
        return empty

    by_category = {}
    grand_total = 0
    grand_checked = 0
    for row in rows:
        cat = row['category']
        total = int(row['total'])
        checked = int(row['checked'])
        by_category[cat] = {'total': total, 'checked': checked}
        grand_total += total
        grand_checked += checked

    pct = round(grand_checked / grand_total * 100) if grand_total else 0
    return {
        'total': grand_total,
        'checked': grand_checked,
        'pct': pct,
        'by_category': by_category,
    }
