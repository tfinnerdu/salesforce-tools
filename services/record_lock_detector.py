import logging
from sf_provider import get_sf

logger = logging.getLogger(__name__)

LOCK_OBJECTS = ['Account', 'Opportunity', 'Case']

def get_locked_records(org: str, sobject: str = None) -> dict:
    """Query ProcessInstance for pending approvals."""
    sf = get_sf(org)
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
