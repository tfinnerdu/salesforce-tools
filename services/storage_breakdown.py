"""Storage breakdown service — record counts for key SF objects."""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_OBJECTS = [
    ('Account WHERE IsPersonAccount = true', 'Account', 'Person Accounts'),
    ('Account WHERE IsPersonAccount = false', 'Account', 'Business Accounts'),
    ('ContactPointEmail', 'ContactPointEmail', 'ContactPoint Emails'),
    ('ContactPointPhone', 'ContactPointPhone', 'ContactPoint Phones'),
    ('ContactPointAddress', 'ContactPointAddress', 'ContactPoint Addresses'),
    ('Individual', 'Individual', 'Individuals'),
    ('Campaign', 'Campaign', 'Campaigns'),
    ('CampaignMember', 'CampaignMember', 'Campaign Members'),
    ('Task', 'Task', 'Tasks'),
    ('Event', 'Event', 'Events'),
    ('Case', 'Case', 'Cases'),
    ('Opportunity', 'Opportunity', 'Opportunities'),
]


def get_record_counts(org: str) -> list:
    """Return record counts for key SF objects."""
    sf = get_sf(org)
    results = []

    for soql_from, object_name, label in _OBJECTS:
        soql = f'SELECT COUNT() FROM {soql_from}'
        try:
            res = sf.query(soql)
            count = res['totalSize']
            results.append({'object': object_name, 'label': label, 'count': count})
        except Exception as exc:
            logger.warning('get_record_counts failed for %s: %s', object_name, exc)
            results.append({'object': object_name, 'label': label, 'count': None, 'error': str(exc)})

    return results
