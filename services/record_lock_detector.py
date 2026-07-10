import logging
from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)

LOCK_OBJECTS = ['Account', 'Opportunity', 'Case']

def get_locked_records(org: str, sobject: str = None) -> dict:
    """Query ProcessInstance for pending approvals."""
    sf = get_sf(org)
    if Config.SHOW_MOCK:
        return _mock_locked(sobject)
    objects = [sobject] if sobject else LOCK_OBJECTS
    results = {}
    for obj in objects:
        try:
            soql = f"SELECT Id, TargetObjectId, Status, CreatedDate, LastModifiedDate FROM ProcessInstance WHERE Status='Pending' AND TargetObject.Type='{obj}' LIMIT 100"
            r = sf.query(soql)
            results[obj] = r.get('records', [])
        except Exception as exc:
            logger.warning('lock query failed for %s: %s', obj, exc)
            results[obj] = []
    total = sum(len(v) for v in results.values())
    return {'total_locked': total, 'by_object': results, 'objects_checked': objects}

def _mock_locked(sobject: str = None) -> dict:
    records = [
        {'Id': 'PI001', 'TargetObjectId': '001XX001', 'Status': 'Pending', 'CreatedDate': '2026-05-10T14:00:00Z', 'LastModifiedDate': '2026-05-10T14:00:00Z'},
        {'Id': 'PI002', 'TargetObjectId': '001XX002', 'Status': 'Pending', 'CreatedDate': '2026-05-12T09:00:00Z', 'LastModifiedDate': '2026-05-12T09:30:00Z'},
    ]
    objs = [sobject] if sobject else LOCK_OBJECTS
    by_obj = {o: (records if o == 'Account' else []) for o in objs}
    return {'total_locked': len(records), 'by_object': by_obj, 'objects_checked': objs}
