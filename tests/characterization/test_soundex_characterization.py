"""
Characterization tests — the Soundex blocking algorithm used by Fuzzy Match.

Soundex is the bucketing key: records only get pairwise-compared if they
share a code. If the algorithm drifts, near-duplicates silently stop being
compared. These pin the classic American Soundex reference values.

If one fails, the Soundex implementation changed — verify against the
American Soundex specification before updating the expected value.
"""
import pytest

from services.fuzzy_matcher import soundex


@pytest.mark.parametrize('name,code', [
    ('Robert',     'R163'),   # classic reference value
    ('Rupert',     'R163'),   # Robert and Rupert share a code — the point of Soundex
    ('Rubin',      'R150'),
    ('Smith',      'S530'),
    ('Smyth',      'S530'),   # Smith/Smyth collide — catches the i/y typo
    ('Tymczak',    'T522'),   # consecutive same-code letters collapse
    ('Ashcraft',   'A261'),   # H rule: letters an H separates merge into one code
    ('Washington', 'W252'),
    ('Pfister',    'P236'),   # first two letters share a code -> second is skipped
])
def test_soundex_reference_values_characterization(name, code):
    assert soundex(name) == code, (
        f"soundex('{name}') changed. American Soundex reference value is '{code}'. "
        f"A drift here means near-duplicates stop landing in the same block."
    )


@pytest.mark.parametrize('value', ['', '   ', '12345', '!!!'])
def test_soundex_no_letters_returns_empty_characterization(value):
    assert soundex(value) == '', (
        "A value with no letters must yield an empty Soundex code so it is "
        "excluded from blocking rather than bucketed with other letterless values."
    )
