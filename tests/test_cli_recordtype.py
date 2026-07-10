"""Unit + characterization tests for services.cli_recordtype.

Pinned against a representative Case record type (tests/fixtures/
Case-Advisee_Case.recordType-meta.xml). NOTE: this fixture follows the standard
RecordType schema/indentation but is provisional until pinned against a real
retrieved record type — the value-encoding caveat (SF percent-encodes some
picklist value names) is confirmed there. Pure string surgery: it adds the
picklist values and leaves every other byte unchanged.
"""
import os
import xml.etree.ElementTree as ET

import pytest

from services import cli_recordtype as RT

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'Case-Advisee_Case.recordType-meta.xml')


def _load():
    with open(FIX, encoding='utf-8') as fh:
        return fh.read()


def test_new_block_for_new_field():
    xml = _load()
    r = RT.add_picklist_values(xml, 'Type_of_Assistance__c', ['Academic', 'Financial'], default='Academic')
    ET.fromstring(r['xml'])
    assert r['mode'] == 'new-block'
    assert '<picklist>Type_of_Assistance__c</picklist>' in r['xml']
    assert r['xml'].count('</picklistValues>') == xml.count('</picklistValues>') + 1
    # tail preserved
    assert r['xml'].endswith(xml[xml.rfind('</picklistValues>') + len('</picklistValues>'):])


def test_new_block_exact_insertion_characterization():
    xml = _load()
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


def test_append_to_existing_field_block():
    xml = _load()
    r = RT.add_picklist_values(xml, 'Priority', ['Urgent', 'High'])  # High already present
    ET.fromstring(r['xml'])
    assert r['mode'] == 'appended'
    assert r['added'] == ['Urgent'] and 'High' in r['skipped']
    assert r['xml'].count('</picklistValues>') == xml.count('</picklistValues>')  # no new block
    # Urgent landed inside the Priority block
    pr = r['xml'].find('<picklist>Priority</picklist>')
    end = r['xml'].find('</picklistValues>', pr)
    assert pr < r['xml'].find('<fullName>Urgent</fullName>') < end


def test_default_marks_one_value():
    r = RT.add_picklist_values(_load(), 'New__c', ['A', 'B'], default='B')
    assert '<fullName>B</fullName>\n            <default>true</default>' in r['xml']
    assert '<fullName>A</fullName>\n            <default>false</default>' in r['xml']


def test_all_values_present_raises():
    with pytest.raises(ValueError):
        RT.add_picklist_values(_load(), 'Priority', ['High', 'Medium', 'Low'])


def test_missing_field_raises():
    with pytest.raises(ValueError):
        RT.add_picklist_values(_load(), '', ['A'])


def test_not_a_recordtype_raises():
    with pytest.raises(ValueError):
        RT.add_picklist_values('<NotARecordType/>', 'F', ['A'])


def test_list_picklists():
    assert RT.list_picklists(_load()) == ['CaseOrigin', 'Priority']


def test_value_is_xml_escaped():
    r = RT.add_picklist_values(_load(), 'X__c', ['A & B'])
    assert '<fullName>A &amp; B</fullName>' in r['xml']
