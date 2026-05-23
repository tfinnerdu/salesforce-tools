"""Apex Code Search service — searches Apex class and trigger bodies for a text pattern."""
import re
import logging

from sf_provider import get_sf
from config import Config

logger = logging.getLogger(__name__)

MAX_FILES = 50


def _mock_search(pattern: str) -> dict:
    """Return a fixed mock result for dev/test mode."""
    return {
        'pattern': pattern,
        'total_files_searched': 8,
        'total_matches': 3,
        'capped': False,
        'matches': [
            {
                'file_type': 'ApexClass',
                'name': 'AccountMigrationService',
                'id': 'AC001',
                'line_number': 42,
                'line': "    acct.SIS_ID__c = sisRecord.personId;",
                'context_before': "    // Populate external IDs",
                'context_after': "    acct.Ethos_Guid__c = sisRecord.guid;",
            },
            {
                'file_type': 'ApexClass',
                'name': 'PersonAccountValidator',
                'id': 'AC002',
                'line_number': 17,
                'line': "    if (String.isBlank(acct.SIS_ID__c)) {",
                'context_before': "    for (Account acct : accounts) {",
                'context_after': "        errors.add('Missing SIS ID on: ' + acct.Id);",
            },
            {
                'file_type': 'ApexTrigger',
                'name': 'AccountBeforeInsert',
                'id': 'TR001',
                'line_number': 8,
                'line': "    String sisId = (String)newAcct.get('SIS_ID__c');",
                'context_before': "trigger AccountBeforeInsert on Account (before insert) {",
                'context_after': "    if (sisId != null) validateSisId(sisId);",
            },
        ],
    }


def _search_body(body: str, pattern: str, case_sensitive: bool) -> list:
    """Return a list of (line_number, line, context_before, context_after) tuples."""
    lines = body.splitlines()
    flags = 0 if case_sensitive else re.IGNORECASE
    hits = []
    for idx, line in enumerate(lines):
        if re.search(re.escape(pattern), line, flags):
            context_before = lines[idx - 1] if idx > 0 else ''
            context_after = lines[idx + 1] if idx < len(lines) - 1 else ''
            hits.append({
                'line_number': idx + 1,
                'line': line,
                'context_before': context_before,
                'context_after': context_after,
            })
    return hits


def search(org: str, pattern: str, case_sensitive: bool = False,
           include_classes: bool = True, include_triggers: bool = True) -> dict:
    """
    Search Apex class and trigger bodies for a text pattern.

    Returns a dict with keys: pattern, matches, total_files_searched, total_matches, capped.
    Each match has: file_type, name, id, line_number, line, context_before, context_after.

    In mock mode, returns a fixed result with 3 matches for any pattern.
    Capped at MAX_FILES (50) total files to prevent timeout.
    """
    if Config.SHOW_MOCK:
        return _mock_search(pattern)

    sf = get_sf(org)
    files_to_search = []

    if include_classes:
        try:
            result = sf.query_all('SELECT Id, Name FROM ApexClass ORDER BY Name')
            for rec in result.get('records', []):
                files_to_search.append({'file_type': 'ApexClass', 'id': rec['Id'], 'name': rec['Name']})
        except Exception as exc:
            logger.warning('Failed to list ApexClass records: %s', exc)

    if include_triggers:
        try:
            result = sf.query_all('SELECT Id, Name FROM ApexTrigger ORDER BY Name')
            for rec in result.get('records', []):
                files_to_search.append({'file_type': 'ApexTrigger', 'id': rec['Id'], 'name': rec['Name']})
        except Exception as exc:
            logger.warning('Failed to list ApexTrigger records: %s', exc)

    capped = len(files_to_search) > MAX_FILES
    files_to_search = files_to_search[:MAX_FILES]
    total_files_searched = len(files_to_search)

    matches = []
    for file_info in files_to_search:
        file_type = file_info['file_type']
        file_id = file_info['id']
        file_name = file_info['name']
        try:
            obj_name = 'ApexClass' if file_type == 'ApexClass' else 'ApexTrigger'
            body_result = sf.restful(
                f'tooling/query',
                params={'q': f"SELECT Body FROM {obj_name} WHERE Id = '{file_id}'"},
            )
            records = body_result.get('records', [])
            if not records:
                continue
            body = records[0].get('Body', '') or ''
            hits = _search_body(body, pattern, case_sensitive)
            for hit in hits:
                matches.append({
                    'file_type': file_type,
                    'name': file_name,
                    'id': file_id,
                    **hit,
                })
        except Exception as exc:
            logger.warning('Failed to fetch body for %s %s: %s', file_type, file_name, exc)

    return {
        'pattern': pattern,
        'total_files_searched': total_files_searched,
        'total_matches': len(matches),
        'capped': capped,
        'matches': matches,
    }
