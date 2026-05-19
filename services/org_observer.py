import logging
from datetime import datetime, timedelta

from db import get_cursor
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_CROSS_ORG_QUERIES = [
    ('PersonAccounts (total)', 'SELECT COUNT() FROM Account WHERE IsPersonAccount = true'),
    ('PersonAccounts w/ SIS ID', 'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null'),
    ('PersonAccounts w/ Ethos GUID', 'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND Ethos_Guid__c != null'),
    ('PersonAccounts w/ Email', 'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND PersonEmail != null'),
    ('ContactPointEmail', 'SELECT COUNT() FROM ContactPointEmail'),
    ('ContactPointPhone', 'SELECT COUNT() FROM ContactPointPhone'),
    ('ContactPointAddress', 'SELECT COUNT() FROM ContactPointAddress'),
]

_LIMIT_DISPLAY_NAMES = {
    'DailyApiRequests': 'Daily API Requests',
    'DataStorageMB': 'Data Storage (MB)',
    'FileStorageMB': 'File Storage (MB)',
    'DailyBulkApiRequests': 'Daily Bulk API Requests',
    'DailyWorkflowEmails': 'Daily Workflow Emails',
    'MassEmail': 'Mass Email',
    'SingleEmail': 'Single Email',
    'DailyDurableStreamingApiEvents': 'Daily Streaming Events',
    'DailyAsyncApexExecutions': 'Daily Async Apex',
    'DailyBulkV2QueryJobs': 'Daily Bulk V2 Query Jobs',
}


def _limit_status(pct: float) -> str:
    if pct < 50:
        return 'green'
    if pct < 80:
        return 'amber'
    return 'red'


def get_limits(org: str) -> dict:
    sf = get_sf(org)
    version = getattr(sf, 'sf_version', None) or '59.0'
    raw = sf.restful(f'limits/', method='GET')
    limits = []
    for key, vals in raw.items():
        if not isinstance(vals, dict) or 'Max' not in vals or 'Remaining' not in vals:
            continue
        max_val = vals['Max']
        remaining = vals['Remaining']
        used = max_val - remaining
        pct = round(100 * used / max_val, 1) if max_val else 0.0
        limits.append({
            'key': key,
            'name': _LIMIT_DISPLAY_NAMES.get(key, key),
            'max': max_val,
            'remaining': remaining,
            'used': used,
            'pct': pct,
            'status': _limit_status(pct),
        })
    limits.sort(key=lambda x: x['name'])
    return {'org': org, 'limits': limits}


def _mock_history(org: str, days: int) -> list:
    base = datetime.utcnow()
    import random
    rng = random.Random(org)
    rows = []
    for i in range(days):
        run_at = base - timedelta(days=days - 1 - i)
        sis_pct = round(min(100, 71 + i * 0.9 + rng.uniform(-1, 1)), 2)
        ethos_pct = round(min(100, 68 + i * 0.85 + rng.uniform(-1, 1)), 2)
        cp_pct = round(min(100, 85 + i * 0.4 + rng.uniform(-0.5, 0.5)), 2)
        overall = round((sis_pct + ethos_pct + cp_pct) / 3, 2)
        rows.append({
            'id': i + 1,
            'org': org,
            'run_at': run_at.isoformat(),
            'overall_pct': overall,
            'results': {
                'checks': [
                    {'check_key': 'sis_id_coverage', 'name': 'SIS ID Coverage', 'pct': sis_pct},
                    {'check_key': 'ethos_guid_coverage', 'name': 'Ethos GUID Coverage', 'pct': ethos_pct},
                    {'check_key': 'contactpoint_parents', 'name': 'ContactPoint Parent Links', 'pct': cp_pct},
                ],
                'overall_pct': overall,
            },
        })
    return rows


def get_quality_trends(org: str, days: int = 30) -> dict:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, org, run_at, results, overall_pct "
                "FROM readiness_runs WHERE org = %s "
                "ORDER BY run_at ASC LIMIT %s",
                (org, days),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("get_quality_trends DB unavailable for org %s: %s", org, exc)
        rows = []

    if not rows:
        rows = _mock_history(org, days)

    labels = []
    series_map: dict = {}

    for row in rows:
        run_at = row.get('run_at')
        if isinstance(run_at, datetime):
            label = run_at.strftime('%Y-%m-%d')
        else:
            label = str(run_at)[:10]
        labels.append(label)

        results = row.get('results') or {}
        checks = results.get('checks') if isinstance(results, dict) else []
        if checks:
            for check in checks:
                key = check.get('check_key') or check.get('name', 'unknown')
                name = check.get('name') or key
                if key not in series_map:
                    series_map[key] = {'name': name, 'values': []}
                series_map[key]['values'].append(round(float(check.get('pct', 0)), 2))

        overall = row.get('overall_pct')
        if overall is not None:
            if 'overall' not in series_map:
                series_map['overall'] = {'name': 'Overall', 'values': []}
            series_map['overall']['values'].append(round(float(overall), 2))

    return {'org': org, 'labels': labels, 'series': list(series_map.values())}


def get_cross_org_counts(orgs: list) -> dict:
    query_labels = [label for label, _ in _CROSS_ORG_QUERIES]
    counts: dict = {}

    for org in orgs:
        counts[org] = {}
        try:
            sf = get_sf(org)
            for label, soql in _CROSS_ORG_QUERIES:
                try:
                    res = sf.query(soql)
                    counts[org][label] = res.get('totalSize', 0)
                except Exception as exc:
                    logger.warning("cross_org query failed org=%s label=%s: %s", org, label, exc)
                    counts[org][label] = None
        except Exception as exc:
            logger.error("get_cross_org_counts failed for org %s: %s", org, exc)
            for label, _ in _CROSS_ORG_QUERIES:
                counts[org][label] = None

    return {'queries': query_labels, 'orgs': orgs, 'counts': counts}
