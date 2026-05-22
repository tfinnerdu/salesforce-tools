import logging
from datetime import datetime
from typing import Optional

from sf_provider import get_sf, assert_orgs_comparable

logger = logging.getLogger(__name__)

ED_CLOUD_OBJECTS = [
    'Account',
    'ContactPointEmail',
    'ContactPointPhone',
    'ContactPointAddress',
    'IndividualApplication',
    'Opportunity',
]


def get_object_schema(sf, object_name: str) -> dict:
    """Fetch describe for object_name and return a field-keyed schema dict."""
    desc = sf.restful(f'sobjects/{object_name}/describe')
    return {
        field['name']: {
            'type': field['type'],
            'required': not field['nillable'],
            'picklistValues': [pv['value'] for pv in field.get('picklistValues', [])],
            'externalId': field.get('externalId', False),
        }
        for field in desc.get('fields', [])
    }


def diff_schemas(schema_left: dict, schema_right: dict) -> dict:
    """Compare two field-keyed schema dicts and return a structured diff."""
    left_fields = set(schema_left.keys())
    right_fields = set(schema_right.keys())

    left_only = sorted(left_fields - right_fields)
    right_only = sorted(right_fields - left_fields)

    type_mismatch = []
    required_mismatch = []
    picklist_mismatch = []

    for field in sorted(left_fields & right_fields):
        l = schema_left[field]
        r = schema_right[field]

        if l['type'] != r['type']:
            type_mismatch.append({
                'field': field,
                'left_type': l['type'],
                'right_type': r['type'],
            })

        if l['required'] != r['required']:
            required_mismatch.append({
                'field': field,
                'left_required': l['required'],
                'right_required': r['required'],
            })

        left_pv = set(l.get('picklistValues', []))
        right_pv = set(r.get('picklistValues', []))
        if left_pv != right_pv:
            picklist_mismatch.append({
                'field': field,
                'left_only_values': sorted(left_pv - right_pv),
                'right_only_values': sorted(right_pv - left_pv),
            })

    total_diffs = (
        len(left_only)
        + len(right_only)
        + len(type_mismatch)
        + len(required_mismatch)
        + len(picklist_mismatch)
    )

    return {
        'left_only': left_only,
        'right_only': right_only,
        'type_mismatch': type_mismatch,
        'required_mismatch': required_mismatch,
        'picklist_mismatch': picklist_mismatch,
        'total_fields_left': len(schema_left),
        'total_fields_right': len(schema_right),
        'total_differences': total_diffs,
    }


def run_diff(left_org: str, right_org: str, objects: Optional[list] = None) -> dict:
    """Run schema diff for a list of objects across two orgs."""
    assert_orgs_comparable(left_org, right_org)
    sf_left = get_sf(left_org)
    sf_right = get_sf(right_org)
    target_objects = objects if objects else ED_CLOUD_OBJECTS

    results = {}
    for obj in target_objects:
        try:
            schema_l = get_object_schema(sf_left, obj)
            schema_r = get_object_schema(sf_right, obj)
            results[obj] = diff_schemas(schema_l, schema_r)
        except Exception as exc:
            logger.error("run_diff: error diffing %s: %s", obj, exc)
            results[obj] = {'error': str(exc)}

    return {
        'left_org': left_org,
        'right_org': right_org,
        'objects': results,
        'run_at': datetime.utcnow().isoformat(),
    }
