"""Fuzzy Match — similarity-based duplicate detection (the DemandTools 'Match' equivalent).

The existing duplicate_radar finds EXACT duplicates (same SIS_ID, same email).
This finds NEAR duplicates — typos, nicknames, transposed characters — that
exact matching misses ("John Smith" vs "Jon Smith").

Records are bucketed by a Soundex blocking key so only plausibly-similar
records are compared pairwise, keeping the scan tractable. Detection only —
no records are modified; review candidates and merge via Validation > Duplicate
Radar.
"""
import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher

from sf_provider import get_sf

logger = logging.getLogger(__name__)

_MAX_RECORDS = 2000   # fuzzy comparison is O(n^2) within blocks — cap the scan
_MAX_BLOCK = 300      # cap a single block's pairwise comparison
_MAX_CANDIDATES = 200

_SOUNDEX_CODES = {
    'B': '1', 'F': '1', 'P': '1', 'V': '1',
    'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
    'D': '3', 'T': '3',
    'L': '4',
    'M': '5', 'N': '5',
    'R': '6',
}


def soundex(value: str) -> str:
    """Return the 4-character American Soundex code for a string ('' if no letters)."""
    letters = re.sub(r'[^A-Za-z]', '', value or '').upper()
    if not letters:
        return ''
    first = letters[0]
    result = first
    prev = _SOUNDEX_CODES.get(first, '')
    for ch in letters[1:]:
        code = _SOUNDEX_CODES.get(ch, '')
        if code and code != prev:
            result += code
            if len(result) >= 4:
                break
        # H and W do not reset the "previous code" — letters they separate merge
        if ch not in ('H', 'W'):
            prev = code
    return (result + '000')[:4]


def _normalize(value) -> str:
    """Lowercase, collapse whitespace — used before similarity scoring."""
    return ' '.join(str(value or '').lower().split())


def similarity(a: str, b: str) -> float:
    """Return a 0.0–1.0 similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def _score_pair(rec_a: dict, rec_b: dict, compare_fields: list) -> tuple:
    """Return (overall_score, {field: score}) comparing two records.

    Fields where BOTH values are empty are excluded — they neither help nor
    penalize. If every compared field is empty on both sides, the score is 0.
    """
    field_scores = {}
    scored = []
    for f in compare_fields:
        va = _normalize(rec_a.get(f))
        vb = _normalize(rec_b.get(f))
        if not va and not vb:
            continue
        s = similarity(va, vb)
        field_scores[f] = round(s, 3)
        scored.append(s)
    overall = sum(scored) / len(scored) if scored else 0.0
    return overall, field_scores


def find_matches(org: str, object_name: str, where_clause: str,
                 compare_fields: list, block_field: str,
                 threshold: float = 0.85) -> dict:
    """Find near-duplicate record pairs above a similarity threshold."""
    if not compare_fields:
        raise ValueError('At least one compare field is required')
    if not block_field:
        raise ValueError('A blocking field is required')
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 0.85
    threshold = min(max(threshold, 0.0), 1.0)

    sf = get_sf(org)
    all_fields = list(dict.fromkeys([block_field] + compare_fields))
    field_list = ', '.join(['Id'] + all_fields)
    soql = (f"SELECT {field_list} FROM {object_name} "
            f"WHERE {where_clause} LIMIT {_MAX_RECORDS}")
    result = sf.query(soql)
    records = result.get('records', [])

    # Block by Soundex of the blocking field
    blocks = defaultdict(list)
    for r in records:
        key = soundex(str(r.get(block_field) or ''))
        if key:
            blocks[key].append(r)

    candidates = []
    comparisons = 0
    truncated_blocks = 0
    for block in blocks.values():
        if len(block) < 2:
            continue
        if len(block) > _MAX_BLOCK:
            truncated_blocks += 1
            block = block[:_MAX_BLOCK]
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                comparisons += 1
                score, field_scores = _score_pair(block[i], block[j], compare_fields)
                if score >= threshold:
                    candidates.append({
                        'a': {'id': block[i].get('Id'),
                              'values': {f: block[i].get(f) for f in all_fields}},
                        'b': {'id': block[j].get('Id'),
                              'values': {f: block[j].get(f) for f in all_fields}},
                        'score': round(score, 3),
                        'field_scores': field_scores,
                    })

    candidates.sort(key=lambda c: c['score'], reverse=True)
    return {
        'object_name': object_name,
        'records_scanned': len(records),
        'block_count': sum(1 for b in blocks.values() if len(b) >= 2),
        'comparisons': comparisons,
        'truncated_blocks': truncated_blocks,
        'threshold': threshold,
        'compare_fields': compare_fields,
        'block_field': block_field,
        'candidate_count': len(candidates),
        'candidates': candidates[:_MAX_CANDIDATES],
    }
