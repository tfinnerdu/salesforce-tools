"""Sandbox Drift Detector — compares identical COUNT() queries across two orgs."""
from datetime import datetime, timezone

from sf_provider import get_sf

DRIFT_CHECKS = [
    # (label, soql)
    ('Person Accounts (total)',       'SELECT COUNT() FROM Account WHERE IsPersonAccount = true'),
    ('Person Accounts w/ SIS ID',     'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null'),
    ('Person Accounts w/ Ethos GUID', 'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND Ethos_Guid__c != null'),
    ('Person Accounts w/ Email',      'SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND PersonEmail != null'),
    ('ContactPoint Emails',           'SELECT COUNT() FROM ContactPointEmail'),
    ('ContactPoint Phones',           'SELECT COUNT() FROM ContactPointPhone'),
    ('ContactPoint Addresses',        'SELECT COUNT() FROM ContactPointAddress'),
    ('Individuals',                   'SELECT COUNT() FROM Individual'),
    ('Active Users',                  'SELECT COUNT() FROM User WHERE IsActive = true'),
    ('Apex Classes',                  'SELECT COUNT() FROM ApexClass'),
    ('Flows (active)',                'SELECT COUNT() FROM FlowDefinition WHERE ActiveVersionId != null'),
]


def _compute_status(baseline_count, target_count, delta_pct):
    """Derive a status string from the counts and computed delta_pct."""
    if baseline_count is not None and baseline_count > 0 and target_count == 0:
        return 'critical'
    if delta_pct is None:
        return 'ok'
    abs_pct = abs(delta_pct)
    if abs_pct > 20:
        return 'critical'
    if abs_pct >= 5:
        return 'warning'
    return 'ok'


def run(baseline_org: str, target_org: str) -> dict:
    """Compare target_org against baseline_org for each DRIFT_CHECKS query.

    Returns {baseline_org, target_org, checks: list, run_at: ISO timestamp}.
    Each check: {label, soql, baseline_count, target_count, delta, delta_pct, status}.
    Interleaves queries (baseline then target per check) to catch connection issues early.
    """
    sf_base = get_sf(baseline_org)
    sf_target = get_sf(target_org)

    results = []
    for label, soql in DRIFT_CHECKS:
        check = {'label': label, 'soql': soql}
        try:
            base_result = sf_base.query(soql)
            baseline_count = base_result['totalSize']
        except Exception as exc:
            check.update({
                'baseline_count': None,
                'target_count': None,
                'delta': None,
                'delta_pct': None,
                'status': 'error',
                'error': str(exc),
            })
            results.append(check)
            continue

        try:
            target_result = sf_target.query(soql)
            target_count = target_result['totalSize']
        except Exception as exc:
            check.update({
                'baseline_count': baseline_count,
                'target_count': None,
                'delta': None,
                'delta_pct': None,
                'status': 'error',
                'error': str(exc),
            })
            results.append(check)
            continue

        delta = target_count - baseline_count
        delta_pct = round((delta / baseline_count) * 100, 1) if baseline_count else None
        status = _compute_status(baseline_count, target_count, delta_pct)

        check.update({
            'baseline_count': baseline_count,
            'target_count': target_count,
            'delta': delta,
            'delta_pct': delta_pct,
            'status': status,
        })
        results.append(check)

    return {
        'baseline_org': baseline_org,
        'target_org': target_org,
        'checks': results,
        'run_at': datetime.now(timezone.utc).isoformat(),
    }
