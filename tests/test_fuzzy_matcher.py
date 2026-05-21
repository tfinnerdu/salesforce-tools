"""Tests for services.fuzzy_matcher — similarity scoring, blocking, find_matches.

The Soundex algorithm itself is pinned by
tests/characterization/test_soundex_characterization.py.
"""
import pytest

from services import fuzzy_matcher


# ── similarity ────────────────────────────────────────────────────────────────

def test_similarity_identical_is_one():
    assert fuzzy_matcher.similarity('john smith', 'john smith') == 1.0


def test_similarity_disjoint_is_low():
    assert fuzzy_matcher.similarity('abc', 'xyz') < 0.2


def test_similarity_typo_is_high():
    assert fuzzy_matcher.similarity('smith', 'smyth') > 0.7


def test_normalize_lowercases_and_collapses():
    assert fuzzy_matcher._normalize('  John   SMITH ') == 'john smith'


# ── _score_pair ───────────────────────────────────────────────────────────────

def test_score_pair_identical_records():
    a = {'FirstName': 'John', 'LastName': 'Smith'}
    score, fs = fuzzy_matcher._score_pair(a, dict(a), ['FirstName', 'LastName'])
    assert score == 1.0
    assert fs['FirstName'] == 1.0


def test_score_pair_excludes_fields_empty_on_both_sides():
    """A field blank on both records is excluded — it neither helps nor hurts."""
    a = {'FirstName': 'John', 'MiddleName': ''}
    b = {'FirstName': 'John', 'MiddleName': ''}
    score, fs = fuzzy_matcher._score_pair(a, b, ['FirstName', 'MiddleName'])
    assert 'MiddleName' not in fs
    assert score == 1.0  # only FirstName counted


def test_score_pair_all_fields_empty_scores_zero():
    a = {'FirstName': '', 'LastName': ''}
    b = {'FirstName': '', 'LastName': ''}
    score, fs = fuzzy_matcher._score_pair(a, b, ['FirstName', 'LastName'])
    assert score == 0.0
    assert fs == {}


def test_score_pair_one_side_empty_scores_low():
    a = {'Name': 'John Smith'}
    b = {'Name': ''}
    score, _ = fuzzy_matcher._score_pair(a, b, ['Name'])
    assert score < 0.2


# ── find_matches ──────────────────────────────────────────────────────────────

class _StubSF:
    def __init__(self, records):
        self._records = records

    def query(self, soql):
        return {'records': self._records}


_NEAR_DUP_RECORDS = [
    {'Id': '001A', 'LastName': 'Smith', 'FirstName': 'John', 'PersonEmail': 'jsmith@doane.edu'},
    {'Id': '001B', 'LastName': 'Smyth', 'FirstName': 'Jon',  'PersonEmail': 'jsmith@doane.edu'},
    {'Id': '001C', 'LastName': 'Jones', 'FirstName': 'Bob',  'PersonEmail': 'bob@doane.edu'},
]


def test_find_matches_detects_near_duplicate(monkeypatch):
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(_NEAR_DUP_RECORDS))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null',
        compare_fields=['FirstName', 'LastName', 'PersonEmail'],
        block_field='LastName', threshold=0.8)
    assert result['records_scanned'] == 3
    assert result['candidate_count'] == 1
    pair = result['candidates'][0]
    ids = {pair['a']['id'], pair['b']['id']}
    assert ids == {'001A', '001B'}        # Smith/Smyth — Jones is in its own block
    assert pair['score'] >= 0.8


def test_find_matches_threshold_excludes_weak_pairs(monkeypatch):
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(_NEAR_DUP_RECORDS))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null',
        compare_fields=['FirstName', 'LastName', 'PersonEmail'],
        block_field='LastName', threshold=0.99)
    assert result['candidate_count'] == 0   # Smith/Smyth scores ~0.89, below 0.99


def test_find_matches_blocking_isolates_different_names(monkeypatch):
    """Records with different Soundex codes are never compared."""
    records = [
        {'Id': '1', 'Name': 'Alice Adams'},
        {'Id': '2', 'Name': 'Zachary Zimmerman'},
    ]
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(records))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null',
        compare_fields=['Name'], block_field='Name', threshold=0.1)
    assert result['comparisons'] == 0       # different blocks — no comparison made
    assert result['candidate_count'] == 0


def test_find_matches_caps_oversized_block(monkeypatch):
    """A block larger than _MAX_BLOCK is truncated and flagged, not exhaustively compared."""
    monkeypatch.setattr(fuzzy_matcher, '_MAX_BLOCK', 3)
    # 5 records that all Soundex to the same block
    records = [{'Id': str(i), 'Name': f'Smith {i}'} for i in range(5)]
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(records))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null', ['Name'], 'Name', threshold=0.99)
    assert result['truncated_blocks'] == 1
    # capped at 3 -> 3 choose 2 = 3 comparisons, not 5 choose 2 = 10
    assert result['comparisons'] == 3


def test_find_matches_requires_compare_fields():
    with pytest.raises(ValueError, match='compare field'):
        fuzzy_matcher.find_matches('dev', 'Account', 'Id != null', [], 'Name')


def test_find_matches_requires_block_field():
    with pytest.raises(ValueError, match='[Bb]locking field'):
        fuzzy_matcher.find_matches('dev', 'Account', 'Id != null', ['Name'], '')


def test_find_matches_threshold_clamped(monkeypatch):
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(_NEAR_DUP_RECORDS))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null', ['Name'], 'LastName', threshold=5.0)
    assert result['threshold'] == 1.0       # clamped into 0..1


def test_find_matches_bad_threshold_defaults(monkeypatch):
    monkeypatch.setattr(fuzzy_matcher, 'get_sf', lambda org: _StubSF(_NEAR_DUP_RECORDS))
    result = fuzzy_matcher.find_matches(
        'dev', 'Account', 'Id != null', ['Name'], 'LastName', threshold='not-a-number')
    assert result['threshold'] == 0.85


# ── Routes ────────────────────────────────────────────────────────────────────

def test_match_page_renders(client):
    assert client.get('/data-ops/match').status_code == 200


def test_match_run_route(client):
    resp = client.post('/data-ops/match/run', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'compare_fields': ['Name'], 'block_field': 'Name', 'threshold': 0.85,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'candidates' in body['data']


def test_match_run_missing_params_returns_400(client):
    resp = client.post('/data-ops/match/run', json={'object': 'Account'})
    assert resp.status_code == 400


def test_match_run_error_returns_500(client, monkeypatch):
    import services.fuzzy_matcher as fm
    monkeypatch.setattr(fm, 'find_matches',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/data-ops/match/run', json={
        'object': 'Account', 'where_clause': 'Id != null',
        'compare_fields': ['Name'], 'block_field': 'Name',
    })
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
