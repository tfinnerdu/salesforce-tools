"""Quick Record Inspector — fetch all field values for a single Salesforce record.

Given an Object name and a Record ID, describes the object to discover queryable
fields, then fetches the record with all non-compound non-base64 fields. Returns
field metadata (name, label, type) alongside the live values so the caller can
render a flat field browser without needing to know the schema in advance.

Useful as a lightweight alternative to Salesforce Inspector for confirming that
a migrated record has the expected field values after a bulk DML operation.
"""
import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_SKIP_TYPES = {'base64', 'address', 'location', 'complexvalue'}


def get_record(org: str, object_name: str, record_id: str,
               external_id_field: str = '') -> dict:
    """Fetch all queryable field values for a single record.

    When ``external_id_field`` is provided (e.g. 'SIS_ID__c'), ``record_id``
    is treated as the external ID value and the lookup uses:
      GET /sobjects/{Object}/{ExternalIdField}/{ExternalIdValue}

    Returns {object, record_id, fields: [{name, label, type, value}],
             total_fields, lookup_mode}.
    """
    if not object_name or not record_id:
        raise ValueError('object_name and record_id are required')

    sf = get_sf(org)

    # Describe to get the full field list.
    desc = sf.restful(f'sobjects/{object_name}/describe')
    queryable_fields = [
        f for f in desc.get('fields', [])
        if f.get('type') not in _SKIP_TYPES
    ]
    field_meta = {f['name']: f for f in queryable_fields}
    field_names = [f['name'] for f in queryable_fields]

    # Build the record path: by Salesforce ID or by external ID.
    if external_id_field:
        record_path = f'sobjects/{object_name}/{external_id_field}/{record_id}'
    else:
        record_path = f'sobjects/{object_name}/{record_id}'

    # Fetch the record.  Salesforce limits the fields= param length; split
    # into batches of 200 and merge the results.
    record: dict = {}
    batch_size = 200
    for i in range(0, len(field_names), batch_size):
        batch = field_names[i:i + batch_size]
        chunk = sf.restful(record_path, params={'fields': ','.join(batch)})
        if isinstance(chunk, dict):
            record.update(chunk)

    if not record:
        raise ValueError(f'Record not found on {object_name} '
                         f'({"external ID" if external_id_field else "ID"}: {record_id})')

    fields = [
        {
            'name': name,
            'label': field_meta[name].get('label', name),
            'type': field_meta[name].get('type', ''),
            'value': record.get(name),
        }
        for name in field_names
    ]
    return {
        'object': object_name,
        'record_id': record.get('Id', record_id),
        'lookup_key': record_id,
        'lookup_mode': f'external_id:{external_id_field}' if external_id_field else 'sf_id',
        'fields': fields,
        'total_fields': len(fields),
    }
