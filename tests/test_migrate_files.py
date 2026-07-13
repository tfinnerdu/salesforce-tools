"""Tests for the pure logic in scripts/migrate_files.py.

The Salesforce I/O is exercised live; here we pin the parent-remap composition
(the crux — old parent Id → new parent Id via a shared external Id) and the
SOQL IN() batching/escaping helpers, which need no org.
"""
from scripts.migrate_files import chunked, compose_parent_map, soql_in_list


# ── compose_parent_map ────────────────────────────────────────────────────────

def test_compose_resolves_via_external_id():
    src_id_to_ext = {'001SRC_A': 'SIS-1', '001SRC_B': 'SIS-2'}
    ext_to_target = {'SIS-1': '001TGT_A', 'SIS-2': '001TGT_B'}
    resolved, unresolved = compose_parent_map(src_id_to_ext, ext_to_target)
    assert resolved == {'001SRC_A': '001TGT_A', '001SRC_B': '001TGT_B'}
    assert unresolved == {}


def test_compose_unresolved_when_source_has_no_ext_id():
    resolved, unresolved = compose_parent_map({'001SRC_A': None}, {})
    assert resolved == {}
    assert '001SRC_A' in unresolved
    assert 'no external-Id' in unresolved['001SRC_A']


def test_compose_unresolved_when_no_target_match():
    resolved, unresolved = compose_parent_map({'001SRC_A': 'SIS-9'}, {'SIS-1': '001TGT_A'})
    assert resolved == {}
    assert 'no target record' in unresolved['001SRC_A']


def test_compose_partial():
    src = {'a': 'X', 'b': 'Y', 'c': None}
    tgt = {'X': 'tX'}  # only X matches
    resolved, unresolved = compose_parent_map(src, tgt)
    assert resolved == {'a': 'tX'}
    assert set(unresolved) == {'b', 'c'}


# ── helpers ───────────────────────────────────────────────────────────────────

def test_chunked_batches():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunked_empty():
    assert list(chunked([], 3)) == []


def test_soql_in_list_quotes_and_escapes():
    # Each value is quoted; a single quote is escaped so it can't break out.
    assert soql_in_list(['a', 'b']) == "'a', 'b'"
    assert soql_in_list(["O'Brien"]) == "'O\\'Brien'"
