"""
Characterization test — cli_recordtype.add_picklist_values byte-exact insertion.

Pins the exact new-block XML + insertion point against the representative
Case-Advisee_Case.recordType-meta.xml fixture. NOTE: per
tests/test_cli_recordtype.py's module docstring, this fixture is
representative, not org-exact, until pinned against a real retrieved record
type — provisional in the same sense that docstring describes. cli_recordtype
does pure string surgery: it adds the picklist values block and leaves every
other byte unchanged.

Moved here from tests/test_cli_recordtype.py (which still covers value
appending, defaults, and validation) to satisfy the Doane
characterization-testing standard's location requirement.
"""
from pathlib import Path

from services import cli_recordtype as RT

_FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'Case-Advisee_Case.recordType-meta.xml'


def test_new_block_exact_insertion_characterization():
    xml = _FIXTURE.read_text(encoding='utf-8')
    r = RT.add_picklist_values(xml, 'Type_of_Assistance__c', ['Academic'], default='Academic')
    expected_block = (
        '\n    <picklistValues>\n'
        '        <picklist>Type_of_Assistance__c</picklist>\n'
        '        <values>\n'
        '            <fullName>Academic</fullName>\n'
        '            <default>true</default>\n'
        '        </values>\n'
        '    </picklistValues>'
    )
    idx = xml.rfind('</picklistValues>') + len('</picklistValues>')
    expected = xml[:idx] + expected_block + xml[idx:]
    assert r['xml'] == expected, (
        'Generated record-type XML diverged from the known-good insertion. '
        'Verify the change is intentional (and re-pin against a real record type).'
    )
