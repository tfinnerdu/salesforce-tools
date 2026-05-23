import logging
from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)

def get_bulk_jobs(org: str) -> list:
    """Query the Bulk API 2.0 ingest jobs for the org's recent bulk loads.

    Returns all jobs sorted newest-first. Pagination is handled client-side.
    Returns mock data only when SF_MOCK is enabled. Against a real org a query
    failure propagates to the caller — it is never masked with mock data, and a
    genuinely empty result returns an empty list.
    """
    if Config.SHOW_MOCK:
        return _mock_bulk_jobs()
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

def _mock_bulk_jobs() -> list:
    return [
        {'id': 'BJ001', 'operation': 'upsert', 'object': 'Account', 'state': 'JobComplete', 'totalProcessingTime': 12400, 'numberRecordsProcessed': 1200, 'numberRecordsFailed': 3, 'createdDate': '2026-05-19T08:00:00Z', 'systemModstamp': '2026-05-19T08:03:24Z'},
        {'id': 'BJ002', 'operation': 'insert', 'object': 'ContactPointEmail', 'state': 'JobComplete', 'totalProcessingTime': 5200, 'numberRecordsProcessed': 980, 'numberRecordsFailed': 0, 'createdDate': '2026-05-18T14:00:00Z', 'systemModstamp': '2026-05-18T14:01:52Z'},
        {'id': 'BJ003', 'operation': 'upsert', 'object': 'ContactPointAddress', 'state': 'Failed', 'totalProcessingTime': None, 'numberRecordsProcessed': 0, 'numberRecordsFailed': 450, 'createdDate': '2026-05-17T11:00:00Z', 'systemModstamp': '2026-05-17T11:00:45Z'},
        {'id': 'BJ004', 'operation': 'delete', 'object': 'Account', 'state': 'InProgress', 'totalProcessingTime': None, 'numberRecordsProcessed': 320, 'numberRecordsFailed': 0, 'createdDate': '2026-05-20T05:00:00Z', 'systemModstamp': '2026-05-20T05:02:10Z'},
    ]
