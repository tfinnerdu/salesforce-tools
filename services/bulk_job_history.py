import logging
from sf_provider import get_sf

logger = logging.getLogger(__name__)

def get_bulk_jobs(org: str) -> list:
    """Query the Bulk API 2.0 ingest jobs for the org's recent bulk loads.

    Returns all jobs sorted newest-first. Pagination is handled client-side.
    A query failure propagates to the caller, and a genuinely empty result
    returns an empty list.
    """
    sf = get_sf(org)
    resp = sf.restful('jobs/ingest')
    jobs = resp.get('records', [])
    mapped = [
        {
            'id': j.get('id'),
            'operation': j.get('operation'),
            'object': j.get('object'),
            'state': j.get('state'),
            'totalProcessingTime': j.get('totalProcessingTime'),
            'numberRecordsProcessed': j.get('numberRecordsProcessed'),
            'numberRecordsFailed': j.get('numberRecordsFailed'),
            'createdDate': j.get('createdDate'),
            'systemModstamp': j.get('systemModstamp'),
        }
        for j in jobs
    ]
    mapped.sort(key=lambda j: j.get('createdDate') or '', reverse=True)
    return mapped
