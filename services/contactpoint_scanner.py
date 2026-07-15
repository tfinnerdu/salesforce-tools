import logging
from datetime import datetime

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_CP_TYPES = ['ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress']

# Ed Cloud's load-bearing architectural invariant: a ContactPoint parents to
# Account (or Individual), NEVER Contact — see CLAUDE.md's Salesforce context.
# Salesforce record IDs are prefixed by SObject type; Account is '001'. A
# non-null ParentId whose ID does not start with '001' is parented to the
# wrong object (typically Contact, '003') and would otherwise report green
# under the old missing-parent-only check.
_ACCOUNT_ID_PREFIX = '001'


def _scan_type(sf, cp_type: str) -> dict:
    """Return counts and sample IDs for a single ContactPoint type."""
    total_res = sf.query(f"SELECT COUNT() FROM {cp_type}")
    total = total_res['totalSize']

    missing_parent_res = sf.query(f"SELECT COUNT() FROM {cp_type} WHERE ParentId = null")
    missing_parent = missing_parent_res['totalSize']

    try:
        missing_indiv_res = sf.query(f"SELECT COUNT() FROM {cp_type} WHERE IndividualId = null")
        missing_individual = missing_indiv_res['totalSize']
    except Exception:
        missing_individual = 0

    try:
        wrong_parent_res = sf.query(
            f"SELECT COUNT() FROM {cp_type} WHERE ParentId != null "
            f"AND NOT ParentId LIKE '{_ACCOUNT_ID_PREFIX}%'"
        )
        wrong_parent_type = wrong_parent_res['totalSize']
    except Exception:
        wrong_parent_type = 0

    sample_res = sf.query(
        f"SELECT Id FROM {cp_type} WHERE ParentId = null LIMIT 5"
    )
    sample_ids = [
        r['Id'] for r in sample_res.get('records', [])
    ][:5]

    wrong_parent_sample_ids = []
    if wrong_parent_type:
        wrong_sample_res = sf.query(
            f"SELECT Id FROM {cp_type} WHERE ParentId != null "
            f"AND NOT ParentId LIKE '{_ACCOUNT_ID_PREFIX}%' LIMIT 5"
        )
        wrong_parent_sample_ids = [
            r['Id'] for r in wrong_sample_res.get('records', [])
        ][:5]

    status = ('green' if missing_parent == 0 and missing_individual == 0
             and wrong_parent_type == 0 else 'red')

    return {
        'missing_parent': missing_parent,
        'missing_individual': missing_individual,
        'wrong_parent_type': wrong_parent_type,
        'total': total,
        'sample_ids': sample_ids,
        'wrong_parent_sample_ids': wrong_parent_sample_ids,
        'status': status,
    }


def scan(org: str) -> dict:
    """Scan all ContactPoint types for missing or wrong-type parent/individual links."""
    sf = get_sf(org)
    result: dict = {}
    total_issues = 0

    for cp_type in _CP_TYPES:
        try:
            stats = _scan_type(sf, cp_type)
            result[cp_type] = stats
            total_issues += (stats['missing_parent'] + stats['missing_individual']
                             + stats['wrong_parent_type'])
        except Exception as exc:
            logger.error("contactpoint_scanner: error scanning %s: %s", cp_type, exc)
            result[cp_type] = {
                'missing_parent': 0,
                'missing_individual': 0,
                'wrong_parent_type': 0,
                'total': 0,
                'sample_ids': [],
                'wrong_parent_sample_ids': [],
                'status': 'error',
                'error': str(exc),
            }

    result['run_at'] = datetime.utcnow().isoformat()
    result['total_issues'] = total_issues
    return result
