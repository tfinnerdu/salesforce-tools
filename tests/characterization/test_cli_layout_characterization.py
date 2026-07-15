"""
Characterization test — cli_layout.add_new_section byte-exact insertion.

Pins the exact new-section XML block + insertion point against the real
Case-Case_Layout.layout-meta.xml fixture retrieved from the Doane sandbox.
cli_layout does pure string surgery on a pasted Layout — it must add the new
section and leave every other byte of the layout unchanged. If the emitted
XML drifts, this fails and names the change.

Moved here from tests/test_cli_layout.py (which still covers add_new_section
across every fixture layout + the add-to-existing-section path) to satisfy
the Doane characterization-testing standard's location requirement.
"""
from pathlib import Path

from services import cli_layout as L

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
PRIMARY = FIXTURES / 'Case-Case_Layout.layout-meta.xml'


def test_add_new_section_is_exact_insertion_characterization():
    xml = PRIMARY.read_text(encoding='utf-8')
    r = L.add_new_section(xml, 'Case Assistance', ['Group_Information__c'], 'Edit')
    expected_section = (
        '\n    <layoutSections>\n'
        '        <customLabel>true</customLabel>\n'
        '        <detailHeading>true</detailHeading>\n'
        '        <editHeading>true</editHeading>\n'
        '        <label>Case Assistance</label>\n'
        '        <layoutColumns>\n'
        '            <layoutItems>\n'
        '                <behavior>Edit</behavior>\n'
        '                <field>Group_Information__c</field>\n'
        '            </layoutItems>\n'
        '        </layoutColumns>\n'
        '        <layoutColumns/>\n'
        '        <style>TwoColumnsLeftToRight</style>\n'
        '    </layoutSections>'
    )
    idx = xml.rfind('</layoutSections>') + len('</layoutSections>')
    expected = xml[:idx] + expected_section + xml[idx:]
    assert r['xml'] == expected, (
        'Generated layout XML diverged from the known-good insertion against the '
        'real Case-Case Layout. Verify the change is intentional before updating.'
    )
