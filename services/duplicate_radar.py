import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional  # noqa: F401 — used in merge()

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _group_by_field(records: list, field: str) -> list:
    """Return list of (value, [ids]) for any value appearing more than once."""
    groups: dict = defaultdict(list)
    for rec in records:
        val = rec.get(field)
        if val:
            groups[val].append(rec.get('Id'))
    return [(val, ids) for val, ids in groups.items() if len(ids) > 1]


def _scan_same_sis_id(sf) -> dict:
    res = sf.query_all(
        "SELECT Id, SIS_ID__c FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null"
    )
    dupes = _group_by_field(res['records'], 'SIS_ID__c')
    records = [{'sis_id': v, 'ids': ids, 'count': len(ids)} for v, ids in dupes]
    return {
        'strategy': 'same_sis_id',
        'label': 'Duplicate SIS ID',
        'count': len(dupes),
        'records': records,
        'status': 'red' if dupes else 'green',
    }


def _scan_same_name_dob(sf) -> dict:
    res = sf.query_all(
        "SELECT Id, Name, PersonBirthdate FROM Account "
        "WHERE IsPersonAccount = true AND PersonBirthdate != null"
    )
    groups: dict = defaultdict(list)
    for rec in res['records']:
        key = f"{rec.get('Name','').lower().strip()}|{rec.get('PersonBirthdate','')}"
        groups[key].append(rec.get('Id'))
    dupes = [(k, ids) for k, ids in groups.items() if len(ids) > 1]
    records = []
    for key, ids in dupes:
        name, dob = key.split('|', 1)
        records.append({'name': name, 'dob': dob, 'ids': ids, 'count': len(ids)})
    return {
        'strategy': 'same_name_dob',
        'label': 'Duplicate Name + Birthdate',
        'count': len(dupes),
        'records': records,
        'status': 'red' if dupes else 'green',
    }


def _scan_same_email(sf) -> dict:
    res = sf.query_all(
        "SELECT Id, PersonEmail FROM Account "
        "WHERE IsPersonAccount = true AND PersonEmail != null"
    )
    dupes = _group_by_field(res['records'], 'PersonEmail')
    records = [{'email': v, 'ids': ids, 'count': len(ids)} for v, ids in dupes]
    return {
        'strategy': 'same_email',
        'label': 'Duplicate Email',
        'count': len(dupes),
        'records': records,
        'status': 'red' if dupes else 'green',
    }


def _scan_same_ethos_guid(sf) -> dict:
    res = sf.query_all(
        "SELECT Id, Ethos_Guid__c FROM Account "
        "WHERE IsPersonAccount = true AND Ethos_Guid__c != null"
    )
    dupes = _group_by_field(res['records'], 'Ethos_Guid__c')
    records = [{'ethos_guid': v, 'ids': ids, 'count': len(ids)} for v, ids in dupes]
    return {
        'strategy': 'same_ethos_guid',
        'label': 'Duplicate Ethos GUID',
        'count': len(dupes),
        'records': records,
        'status': 'red' if dupes else 'green',
    }


def _edit_distance(a: str, b: str) -> int:
    """Wagner-Fischer edit distance between two strings."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[lb]


def _scan_fuzzy_name(sf) -> dict:
    res = sf.query_all(
        "SELECT Id, Name FROM Account WHERE IsPersonAccount = true AND Name != null"
    )
    records = [(r['Name'].strip(), r['Id']) for r in res['records'] if r.get('Name')]

    # Group by first 3 chars to limit O(n²) comparisons
    prefix_groups: dict = defaultdict(list)
    for name, rec_id in records:
        key = name[:3].lower()
        prefix_groups[key].append((name, rec_id))

    pairs = []
    seen: set = set()
    for group in prefix_groups.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                name_a, id_a = group[i]
                name_b, id_b = group[j]
                if name_a == name_b:
                    continue
                pair_key = tuple(sorted([id_a, id_b]))
                if pair_key in seen:
                    continue
                dist = _edit_distance(name_a.lower(), name_b.lower())
                if dist <= 2:
                    seen.add(pair_key)
                    pairs.append({
                        'name_a': name_a,
                        'id_a': id_a,
                        'name_b': name_b,
                        'id_b': id_b,
                        'edit_distance': dist,
                    })

    return {
        'strategy': 'fuzzy_name',
        'label': 'Fuzzy Name Match (edit distance ≤ 2)',
        'count': len(pairs),
        'records': pairs,
        'status': 'red' if pairs else 'green',
    }


def scan(org: str) -> dict:
    sf = get_sf(org)
    strategies = [
        _scan_same_sis_id(sf),
        _scan_same_name_dob(sf),
        _scan_same_email(sf),
        _scan_same_ethos_guid(sf),
        _scan_fuzzy_name(sf),
    ]
    total_groups = sum(s['count'] for s in strategies)
    return {
        'strategies': strategies,
        'total_groups': total_groups,
        'run_at': datetime.utcnow().isoformat(),
    }


def merge(org: str, master_id: str, victim_id: str, bypass: bool = False) -> dict:
    from sf_provider import dml_guard
    sf = get_sf(org)
    exc_for_log: Optional[Exception] = None
    try:
        with dml_guard(sf, bypass=bypass):
            sf.Account.merge(master_id, [victim_id])
        success = True
    except Exception as exc:
        logger.error("merge failed master=%s victim=%s: %s", master_id, victim_id, exc)
        exc_for_log = exc
        success = False

    if success:
        try:
            from services import merge_history
            merge_history._ensure_table()
            merge_history.log_merge(
                org=org, master_id=master_id, victim_id=victim_id,
                bypass_used=bypass, status='success'
            )
        except Exception:
            pass  # non-fatal
    else:
        try:
            from services import merge_history
            merge_history._ensure_table()
            merge_history.log_merge(
                org=org, master_id=master_id, victim_id=victim_id,
                bypass_used=bypass, status='error',
                error_msg=str(exc_for_log) if exc_for_log else 'unknown error'
            )
        except Exception:
            pass  # non-fatal

    return {
        'success': success,
        'master_id': master_id,
        'merged_victim_id': victim_id,
    }
