"""
Characterization test — ContactPoint must parent to Account, never Contact.

This pins the exact load-bearing Ed Cloud invariant CLAUDE.md calls out
("ContactPoint records parent to Account/Individual via Master-Detail, NOT to
Contact") as a "known-bad" assertion per the Doane characterization-testing
standard: for a wrong value that's worse than a missing one, assert the
known-bad case can never silently pass.

Before this test existed, services/contactpoint_scanner.py only checked
`WHERE ParentId = null` -- a ContactPoint with a non-null ParentId pointing at
a Contact record (id prefix 003) instead of an Account (001) reported green.
This test would have caught that gap; it now guards the fix
(contactpoint_scanner._scan_type's wrong-parent-type check) from regressing.
"""
from unittest.mock import MagicMock

from services import contactpoint_scanner


def _sf_with_contact_parented_record():
    """A ContactPointEmail record whose ParentId is a Contact id (003...),
    not an Account id (001...) -- the known-bad case."""
    sf = MagicMock()

    def query(soql):
        if 'COUNT()' in soql and "NOT ParentId LIKE '001%'" in soql:
            return {'totalSize': 1, 'done': True, 'records': []}
        if 'Id' in soql and "NOT ParentId LIKE '001%'" in soql and 'LIMIT 5' in soql:
            return {'totalSize': 1, 'done': True,
                    'records': [{'Id': '003000000000001AAA'}]}
        return {'totalSize': 0, 'done': True, 'records': []}

    sf.query.side_effect = query
    return sf


def test_contactpoint_parented_to_contact_is_flagged_not_silently_green_characterization():
    """
    KNOWN-BAD CASE: a ContactPointEmail record with ParentId = a Contact id
    (003 prefix). Ed Cloud's architecture requires ContactPoint -> Account,
    never Contact. This must never report 'green' / zero issues.
    """
    result = contactpoint_scanner._scan_type(_sf_with_contact_parented_record(), 'ContactPointEmail')

    assert result['wrong_parent_type'] == 1, (
        'A ContactPoint parented to a Contact (id prefix 003) instead of an Account '
        '(001) must be counted as a wrong-parent-type issue. If this assertion fails, '
        'the wrong-parent-type detection query in contactpoint_scanner._scan_type has '
        'regressed and a mis-parented ContactPoint would silently report green again.'
    )
    assert result['status'] == 'red', (
        'A record known to violate the ContactPoint-parents-to-Account invariant must '
        'never report an overall green status.'
    )
    assert result['wrong_parent_sample_ids'] == ['003000000000001AAA'], (
        'The offending record id must surface in wrong_parent_sample_ids so an admin '
        'can actually find and fix it, not just see a count.'
    )


def test_contactpoint_parented_to_account_is_not_flagged_characterization():
    """Sanity companion: a correctly-parented ContactPoint (Account, 001
    prefix) must NOT be flagged, so the check doesn't just always say red."""
    sf = MagicMock()
    sf.query.return_value = {'totalSize': 0, 'done': True, 'records': []}
    result = contactpoint_scanner._scan_type(sf, 'ContactPointEmail')
    assert result['wrong_parent_type'] == 0
    assert result['status'] == 'green'
