import json
import logging
from datetime import datetime
from typing import Optional

from db import get_cursor
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def _status(pct: float) -> str:
    if pct >= 100:
        return 'green'
    if pct >= 90:
        return 'amber'
    return 'red'


def _issue_status(count: int) -> str:
    if count == 0:
        return 'green'
    if count <= 25:
        return 'amber'
    return 'red'


def check_sis_id_coverage(sf) -> dict:
    total_res = sf.query("SELECT COUNT() FROM Account WHERE IsPersonAccount = true")
    total = total_res['totalSize']
    covered_res = sf.query(
        "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null"
    )
    covered = covered_res['totalSize']
    pct = round(100 * covered / total, 2) if total else 0.0
    return {
        'name': 'SIS ID Coverage',
        'check_key': 'sis_id_coverage',
        'total': total,
        'covered': covered,
        'pct': pct,
        'status': _status(pct),
        'detail': f'{covered:,} of {total:,} PersonAccounts have a SIS_ID__c value',
    }


def check_ethos_guid_coverage(sf) -> dict:
    total_res = sf.query("SELECT COUNT() FROM Account WHERE IsPersonAccount = true")
    total = total_res['totalSize']
    covered_res = sf.query(
        "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND Ethos_Guid__c != null"
    )
    covered = covered_res['totalSize']
    pct = round(100 * covered / total, 2) if total else 0.0
    return {
        'name': 'Ethos GUID Coverage',
        'check_key': 'ethos_guid_coverage',
        'total': total,
        'covered': covered,
        'pct': pct,
        'status': _status(pct),
        'detail': f'{covered:,} of {total:,} PersonAccounts have an Ethos_Guid__c value',
    }


def check_contactpoint_parents(sf) -> dict:
    email_res = sf.query("SELECT COUNT() FROM ContactPointEmail WHERE ParentId = null")
    phone_res = sf.query("SELECT COUNT() FROM ContactPointPhone WHERE ParentId = null")
    addr_res = sf.query("SELECT COUNT() FROM ContactPointAddress WHERE ParentId = null")

    total_email = sf.query("SELECT COUNT() FROM ContactPointEmail")['totalSize']
    total_phone = sf.query("SELECT COUNT() FROM ContactPointPhone")['totalSize']
    total_addr = sf.query("SELECT COUNT() FROM ContactPointAddress")['totalSize']

    total = total_email + total_phone + total_addr
    broken = email_res['totalSize'] + phone_res['totalSize'] + addr_res['totalSize']
    covered = total - broken
    pct = round(100 * covered / total, 2) if total else 0.0
    return {
        'name': 'ContactPoint Parent Links',
        'check_key': 'contactpoint_parents',
        'total': total,
        'covered': covered,
        'pct': pct,
        'status': _status(pct),
        'detail': (
            f'{broken:,} ContactPoint records missing ParentId '
            f'(Email: {email_res["totalSize"]}, Phone: {phone_res["totalSize"]}, '
            f'Address: {addr_res["totalSize"]})'
        ),
    }


def check_required_fields(sf) -> dict:
    total_res = sf.query("SELECT COUNT() FROM Account WHERE IsPersonAccount = true")
    total = total_res['totalSize']
    missing_res = sf.query(
        "SELECT COUNT() FROM Account WHERE IsPersonAccount = true "
        "AND (FirstName = null OR LastName = null OR RecordTypeId = null)"
    )
    missing = missing_res['totalSize']
    covered = total - missing
    pct = round(100 * covered / total, 2) if total else 0.0
    return {
        'name': 'Required Fields',
        'check_key': 'required_fields',
        'total': total,
        'covered': covered,
        'pct': pct,
        'status': _status(pct),
        'detail': (
            f'{missing:,} PersonAccounts missing FirstName, LastName, or RecordTypeId'
        ),
    }


def check_duplicates(sf) -> dict:
    # Fetch records and group by SIS_ID__c in Python to find duplicates
    res = sf.query_all(
        "SELECT Id, SIS_ID__c FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null"
    )
    from collections import Counter
    sis_counts = Counter(
        r['SIS_ID__c'] for r in res['records'] if r.get('SIS_ID__c')
    )
    dup_groups = sum(1 for cnt in sis_counts.values() if cnt > 1)
    total = res['totalSize']
    pct = round(100 * (total - dup_groups) / total, 2) if total else 100.0
    return {
        'name': 'Duplicate SIS IDs',
        'check_key': 'duplicates',
        'total': total,
        'covered': 0,
        'pct': pct,
        'status': _issue_status(dup_groups),
        'detail': f'{dup_groups} duplicate SIS_ID__c groups found across {total:,} PersonAccounts',
    }


def check_individual_links(sf) -> dict:
    email_res = sf.query("SELECT COUNT() FROM ContactPointEmail WHERE IndividualId = null")
    phone_res = sf.query("SELECT COUNT() FROM ContactPointPhone WHERE IndividualId = null")
    addr_res = sf.query("SELECT COUNT() FROM ContactPointAddress WHERE IndividualId = null")

    total_email = sf.query("SELECT COUNT() FROM ContactPointEmail")['totalSize']
    total_phone = sf.query("SELECT COUNT() FROM ContactPointPhone")['totalSize']
    total_addr = sf.query("SELECT COUNT() FROM ContactPointAddress")['totalSize']

    total = total_email + total_phone + total_addr
    broken = email_res['totalSize'] + phone_res['totalSize'] + addr_res['totalSize']
    covered = total - broken
    pct = round(100 * covered / total, 2) if total else 0.0
    return {
        'name': 'Individual Links',
        'check_key': 'individual_links',
        'total': total,
        'covered': covered,
        'pct': pct,
        'status': _status(pct),
        'detail': (
            f'{broken:,} ContactPoint records missing IndividualId '
            f'(Email: {email_res["totalSize"]}, Phone: {phone_res["totalSize"]}, '
            f'Address: {addr_res["totalSize"]})'
        ),
    }


def run_full_readiness_check(org: str) -> dict:
    sf = get_sf(org)
    checks = [
        check_sis_id_coverage(sf),
        check_ethos_guid_coverage(sf),
        check_contactpoint_parents(sf),
        check_required_fields(sf),
        check_duplicates(sf),
        check_individual_links(sf),
    ]
    overall_pct = round(sum(c['pct'] for c in checks) / len(checks), 2)
    if any(c['status'] == 'red' for c in checks):
        overall_status = 'red'
    elif any(c['status'] == 'amber' for c in checks):
        overall_status = 'amber'
    else:
        overall_status = 'green'
    return {
        'checks': checks,
        'overall_pct': overall_pct,
        'overall_status': overall_status,
        'run_at': datetime.utcnow().isoformat(),
    }


def save_run(org: str, result: dict) -> None:
    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO readiness_runs (org, results, overall_pct) VALUES (%s, %s, %s)",
                (org, json.dumps(result), result.get('overall_pct')),
            )
    except Exception as exc:
        logger.error("save_run failed for org %s: %s", org, exc)


def get_history(org: str, limit: int = 30) -> list:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, org, run_at, results, overall_pct "
                "FROM readiness_runs WHERE org = %s ORDER BY run_at DESC LIMIT %s",
                (org, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("get_history failed for org %s: %s", org, exc)
        return []
