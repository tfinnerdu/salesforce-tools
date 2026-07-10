"""
Characterization tests — Data Tune standardization rules.

Each rule is a pure string->string transformation. These tests pin a
known input to a known output. If a rule's behavior changes, exactly one
of these fails and names what changed — forcing a conscious decision
rather than a silent shift in how thousands of records get normalized.

When a failure is an intentional rule change, update the expected value
AND the comment, and note when/why it changed.
"""
import pytest

from services import data_tuner


# ── trim ──────────────────────────────────────────────────────────────────────

def test_trim_characterization():
    assert data_tuner.apply_rules('  John   Smith  ', ['trim']) == 'John Smith', (
        "The 'trim' rule must collapse internal whitespace runs and strip the ends."
    )


# ── proper_case ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('JOHN SMITH',   'John Smith'),     # all caps -> proper
    ('john smith',   'John Smith'),     # all lower -> proper
    ("o'brien",      "O'Brien"),        # apostrophe: capitalize after '
    ('smith-jones',  'Smith-Jones'),    # hyphen: capitalize after -
    ('mcdonald',     'McDonald'),       # Mc prefix special case
])
def test_proper_case_characterization(raw, expected):
    assert data_tuner.apply_rules(raw, ['proper_case']) == expected, (
        f"proper_case('{raw}') changed. Known-good output was '{expected}'. "
        f"Verify the name-casing change is intentional before updating."
    )


# ── title_case ────────────────────────────────────────────────────────────────

def test_title_case_characterization():
    assert data_tuner.apply_rules('the QUICK brown', ['title_case']) == 'The Quick Brown'


# ── upper / lower ─────────────────────────────────────────────────────────────

def test_upper_characterization():
    assert data_tuner.apply_rules('ne', ['upper']) == 'NE'


def test_lower_characterization():
    assert data_tuner.apply_rules('ABC', ['lower']) == 'abc'


# ── lowercase_email ───────────────────────────────────────────────────────────

def test_lowercase_email_characterization():
    assert data_tuner.apply_rules('  John.Doe@DOANE.edu  ', ['lowercase_email']) == 'john.doe@doane.edu'


# ── phone_us ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('402.555.1234',      '(402) 555-1234'),   # dotted 10-digit
    ('1-402-555-1234',    '(402) 555-1234'),   # 11-digit, leading country code 1
    ('(402) 555-1234',    '(402) 555-1234'),   # already formatted — idempotent
    ('555-1234',          '555-1234'),         # only 7 digits — left unchanged
    ('not a phone',       'not a phone'),      # no digits — left unchanged
])
def test_phone_us_characterization(raw, expected):
    assert data_tuner.apply_rules(raw, ['phone_us']) == expected, (
        f"phone_us('{raw}') changed. Known-good output was '{expected}'."
    )


# ── state_abbrev ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('Nebraska',  'NE'),
    ('nebraska',  'NE'),       # case-insensitive
    ('  Iowa  ',  'IA'),       # trimmed before lookup
    ('Narnia',    'Narnia'),   # not a real state — left unchanged
])
def test_state_abbrev_characterization(raw, expected):
    assert data_tuner.apply_rules(raw, ['state_abbrev']) == expected


# ── rule chaining ─────────────────────────────────────────────────────────────

def test_rule_chaining_applies_in_order_characterization():
    """Rules apply left-to-right: trim then proper_case."""
    assert data_tuner.apply_rules('  JOHN   SMITH  ', ['trim', 'proper_case']) == 'John Smith'


# ── rule registry ─────────────────────────────────────────────────────────────

KNOWN_RULE_NAMES = {
    'trim', 'proper_case', 'title_case', 'upper', 'lower',
    'lowercase_email', 'phone_us', 'state_abbrev',
}


def test_rule_registry_contract_characterization():
    """The set of rule names is a UI contract — mc-data-ops-snippet.js renders them."""
    names = {r['name'] for r in data_tuner.list_rules()}
    assert names == KNOWN_RULE_NAMES, (
        "The Tune rule set changed. The Tune UI builds its rule multi-select from "
        "list_rules(); update KNOWN_RULE_NAMES and verify the UI still renders."
    )
