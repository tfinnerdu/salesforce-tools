"""Regression test suite runner.

DB table (created on first use by _ensure_table()):

    CREATE TABLE IF NOT EXISTS regression_suites (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        assertions  JSONB NOT NULL DEFAULT '[]',
        baseline    JSONB,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
"""
import json
import logging
from datetime import datetime

from db import get_cursor
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS regression_suites (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    assertions  JSONB NOT NULL DEFAULT '[]',
    baseline    JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


def _ensure_table() -> None:
    try:
        with get_cursor() as cur:
            cur.execute(_TABLE_DDL)
    except Exception as exc:
        logger.error("regression_tester _ensure_table failed: %s", exc)
        raise


def list_suites() -> list:
    _ensure_table()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, assertions, baseline, created_at FROM regression_suites ORDER BY id DESC"
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def save_suite(name: str, assertions: list) -> dict:
    _ensure_table()
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO regression_suites (name, assertions) VALUES (%s, %s) RETURNING id, name, assertions, created_at",
            (name, json.dumps(assertions)),
        )
        row = cur.fetchone()
    return dict(row)


def run_suite(org: str, suite_id: int) -> dict:
    _ensure_table()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, assertions, baseline FROM regression_suites WHERE id = %s",
            (suite_id,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Suite {suite_id} not found")

    suite = dict(row)
    assertions = suite['assertions'] if isinstance(suite['assertions'], list) else json.loads(suite['assertions'] or '[]')
    baseline = suite['baseline'] if isinstance(suite['baseline'], dict) else json.loads(suite['baseline'] or '{}')

    sf = get_sf(org)
    results = []
    for assertion in assertions:
        label = assertion.get('label', '')
        soql = assertion.get('soql', '')
        expected = assertion.get('expected_count')
        baseline_count = baseline.get(label)

        try:
            res = sf.query(soql)
            actual = res.get('totalSize', 0)
        except Exception as exc:
            logger.warning("Assertion '%s' query failed: %s", label, exc)
            results.append({
                'label': label,
                'soql': soql,
                'expected_count': expected,
                'baseline_count': baseline_count,
                'actual_count': None,
                'status': 'error',
                'error': str(exc),
            })
            continue

        if baseline_count is not None:
            passed = actual == baseline_count
            status = 'pass' if passed else 'fail'
        elif expected is not None:
            passed = actual == expected
            status = 'pass' if passed else 'fail'
        else:
            status = 'info'

        results.append({
            'label': label,
            'soql': soql,
            'expected_count': expected,
            'baseline_count': baseline_count,
            'actual_count': actual,
            'status': status,
        })

    pass_count = sum(1 for r in results if r['status'] == 'pass')
    fail_count = sum(1 for r in results if r['status'] == 'fail')
    error_count = sum(1 for r in results if r['status'] == 'error')

    return {
        'suite_id': suite_id,
        'suite_name': suite['name'],
        'org': org,
        'run_at': datetime.utcnow().isoformat(),
        'results': results,
        'summary': {
            'pass': pass_count,
            'fail': fail_count,
            'error': error_count,
            'total': len(results),
        },
    }


def save_baseline(org: str, suite_id: int) -> dict:
    _ensure_table()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, assertions FROM regression_suites WHERE id = %s",
            (suite_id,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Suite {suite_id} not found")

    assertions = row['assertions'] if isinstance(row['assertions'], list) else json.loads(row['assertions'] or '[]')
    sf = get_sf(org)
    baseline = {}
    for assertion in assertions:
        label = assertion.get('label', '')
        soql = assertion.get('soql', '')
        try:
            res = sf.query(soql)
            baseline[label] = res.get('totalSize', 0)
        except Exception as exc:
            logger.warning("Baseline capture failed for '%s': %s", label, exc)
            baseline[label] = None

    with get_cursor() as cur:
        cur.execute(
            "UPDATE regression_suites SET baseline = %s WHERE id = %s",
            (json.dumps(baseline), suite_id),
        )

    return {
        'suite_id': suite_id,
        'org': org,
        'captured_at': datetime.utcnow().isoformat(),
        'baseline': baseline,
    }
