import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)

CHECKS = [
    {
        'key': 'cpe_no_account',
        'label': 'ContactPointEmail — missing Account',
        'soql': "SELECT Id, EmailAddress FROM ContactPointEmail WHERE ParentId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM ContactPointEmail WHERE ParentId = null",
        'description': 'ContactPointEmail records must parent to a Person Account via ParentId.',
    },
    {
        'key': 'cpp_no_account',
        'label': 'ContactPointPhone — missing Account',
        'soql': "SELECT Id, TelephoneNumber FROM ContactPointPhone WHERE ParentId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM ContactPointPhone WHERE ParentId = null",
        'description': 'ContactPointPhone records must parent to a Person Account via ParentId.',
    },
    {
        'key': 'cpa_no_account',
        'label': 'ContactPointAddress — missing Account',
        'soql': "SELECT Id, Street, City FROM ContactPointAddress WHERE ParentId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM ContactPointAddress WHERE ParentId = null",
        'description': 'ContactPointAddress records must parent to a Person Account via ParentId.',
    },
    {
        'key': 'cpe_no_individual',
        'label': 'ContactPointEmail — missing Individual',
        'soql': "SELECT Id, EmailAddress FROM ContactPointEmail WHERE IndividualId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM ContactPointEmail WHERE IndividualId = null",
        'description': 'ContactPointEmail records should link to an Individual for consent/privacy compliance.',
    },
    {
        'key': 'cpp_no_individual',
        'label': 'ContactPointPhone — missing Individual',
        'soql': "SELECT Id, TelephoneNumber FROM ContactPointPhone WHERE IndividualId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM ContactPointPhone WHERE IndividualId = null",
        'description': 'ContactPointPhone records should link to an Individual for consent tracking.',
    },
    {
        'key': 'pa_no_individual',
        'label': 'Person Account — no linked Individual',
        'soql': "SELECT Id, Name FROM Account WHERE IsPersonAccount = true AND IndividualId = null LIMIT 50",
        'count_soql': "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND IndividualId = null",
        'description': 'Person Accounts should have an associated Individual for Data Protection compliance.',
    },
]


def scan(org: str) -> list:
    """Run all orphan checks. Returns list of check results."""
    sf = get_sf(org)
    results = []

    for check in CHECKS:
        try:
            count_res = sf.query(check['count_soql'])
            count = count_res['totalSize']

            samples = []
            if count > 0:
                sample_res = sf.query(check['soql'])
                samples = [dict(r) for r in sample_res['records'][:10]]

            status = 'ok' if count == 0 else 'warning'
            results.append({
                'key': check['key'],
                'label': check['label'],
                'description': check['description'],
                'count': count,
                'status': status,
                'samples': samples,
            })
        except Exception as exc:
            logger.error('orphan_scanner: check %s failed: %s', check['key'], exc)
            results.append({
                'key': check['key'],
                'label': check['label'],
                'description': check['description'],
                'count': 0,
                'status': 'error',
                'samples': [],
                'error': str(exc),
            })

    return results
