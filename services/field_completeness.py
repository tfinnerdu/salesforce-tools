"""Field completeness service — fill-rate check for migration-critical fields."""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)

# (object, field, label, where_clause)
CHECKS = [
    ('Account', 'SIS_ID__c', 'SIS ID', 'WHERE IsPersonAccount = true'),
    ('Account', 'Ethos_Guid__c', 'Ethos GUID', 'WHERE IsPersonAccount = true'),
    ('Account', 'PersonEmail', 'Email', 'WHERE IsPersonAccount = true'),
    ('Account', 'PersonBirthdate', 'Birthdate', 'WHERE IsPersonAccount = true'),
    ('Account', 'Phone', 'Phone', 'WHERE IsPersonAccount = true'),
    ('Account', 'BillingStreet', 'Billing Street', 'WHERE IsPersonAccount = false'),
    ('ContactPointEmail', 'EmailAddress', 'Email Address', ''),
    ('ContactPointPhone', 'TelephoneNumber', 'Phone Number', ''),
    ('ContactPointAddress', 'Street', 'Street', ''),
    ('Individual', 'FirstName', 'First Name', ''),
]


def _status(pct: float) -> str:
    if pct >= 95:
        return 'green'
    if pct >= 75:
        return 'amber'
    return 'red'


def run(org: str) -> list:
    """Check fill rate for migration-critical fields."""
    sf = get_sf(org)
    results = []

    for obj, field, label, where_clause in CHECKS:
        try:
            total_soql = f'SELECT COUNT() FROM {obj} {where_clause}'.strip()
            total_res = sf.query(total_soql)
            total = total_res['totalSize']

            if where_clause:
                populated_soql = f'SELECT COUNT() FROM {obj} {where_clause} AND {field} != null'
            else:
                populated_soql = f'SELECT COUNT() FROM {obj} WHERE {field} != null'

            populated_res = sf.query(populated_soql)
            populated = populated_res['totalSize']

            missing = total - populated
            pct = round(100.0 * populated / total, 2) if total else 0.0
            status = _status(pct)

            results.append({
                'object': obj,
                'field': field,
                'label': label,
                'total': total,
                'populated': populated,
                'missing': missing,
                'pct': pct,
                'status': status,
            })
        except Exception as exc:
            logger.warning('field_completeness check failed for %s.%s: %s', obj, field, exc)
            results.append({
                'object': obj,
                'field': field,
                'label': label,
                'total': 0,
                'populated': 0,
                'missing': 0,
                'pct': 0.0,
                'status': 'error',
                'error': str(exc),
            })

    return results
