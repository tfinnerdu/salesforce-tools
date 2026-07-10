import logging
from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)

# Fields considered safe to scrub (expand as needed)
ANONYMIZABLE_FIELDS = {
    'Account': ['Name', 'PersonEmail', 'PersonBirthdate', 'Phone', 'SIS_ID__c'],
    'ContactPointEmail': ['EmailAddress'],
    'ContactPointPhone': ['TelephoneNumber'],
    'ContactPointAddress': ['Street', 'City', 'PostalCode'],
}


def list_objects() -> list:
    """Return objects with anonymizable field definitions."""
    return [
        {'object': obj, 'fields': fields}
        for obj, fields in ANONYMIZABLE_FIELDS.items()
    ]


def preview(org: str, object_name: str, field_names: list) -> dict:
    """Return a COUNT of records that would be affected — no PII returned."""
    sf = get_sf(org)
    where = ' AND '.join(f'{f} != null' for f in field_names) if field_names else 'Id != null'
    soql = f'SELECT COUNT() FROM {object_name} WHERE {where}'
    try:
        result = sf.query(soql)
        count = result.get('totalSize', 0)
    except Exception as exc:
        logger.warning('preview query failed: %s', exc)
        count = 0
    return {
        'object': object_name,
        'fields': field_names,
        'record_count': count,
        'soql': soql,
    }


def run(org: str, object_name: str, field_names: list, dry_run: bool = True) -> dict:
    """
    Stub: log what would be sent to PII_SERVICE_URL.
    When PII_SERVICE_URL is configured, this is where the real call goes.
    """
    pii_url = Config.PII_SERVICE_URL
    prev = preview(org=org, object_name=object_name, field_names=field_names)
    record_count = prev['record_count']

    payload = {
        'org': org,
        'object': object_name,
        'fields': field_names,
        'record_count': record_count,
        'dry_run': dry_run,
    }

    if not pii_url:
        logger.info('Anonymizer stub (no PII_SERVICE_URL): would send %s', payload)
        return {
            'status': 'stub',
            'message': 'PII_SERVICE_URL not configured — no records were modified.',
            'would_affect': record_count,
            'payload': payload,
        }

    if dry_run:
        logger.info('Anonymizer dry-run to %s: %s', pii_url, payload)
        return {
            'status': 'dry_run',
            'message': f'Dry run — would send {record_count} records to {pii_url}',
            'would_affect': record_count,
            'payload': payload,
        }

    # TODO: Wire real PII service call here
    # import requests
    # resp = requests.post(pii_url, json=payload, timeout=30)
    # resp.raise_for_status()
    # return {'status': 'sent', 'would_affect': record_count, 'response': resp.json()}
    logger.warning('Anonymizer live run not yet wired — treating as dry_run')
    return {
        'status': 'not_wired',
        'message': 'Live anonymization not yet wired. Uncomment the requests.post block in anonymizer.py.',
        'would_affect': record_count,
        'payload': payload,
    }
