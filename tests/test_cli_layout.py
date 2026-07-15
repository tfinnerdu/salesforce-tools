"""Unit + characterization tests for services.cli_layout (page-layout clone).

Pinned against the real Case page layouts retrieved from the Doane sandbox
(tests/fixtures/Case-*.layout-meta.xml). Pure string surgery: it must add the
new fields and leave every other byte of the layout unchanged.
"""
import glob
import os
import xml.etree.ElementTree as ET

import pytest

from services import cli_layout as L

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
PRIMARY = os.path.join(FIXTURES, 'Case-Case_Layout.layout-meta.xml')


def _load(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _all_layouts():
    return sorted(glob.glob(os.path.join(FIXTURES, 'Case-*.layout-meta.xml')))


# ── add_new_section across every real layout ──────────────────────────────────

@pytest.mark.parametrize('path', _all_layouts())
def test_add_new_section_preserves_everything(path):
    xml = _load(path)
    r = L.add_new_section(xml, 'Case Assistance',
                          ['Case.Group_Information__c', 'Occurrence_Date__c'], 'Edit')
    out = r['xml']
    ET.fromstring(out)  # still valid XML
    assert out.count('</layoutSections>') == xml.count('</layoutSections>') + 1
    assert '<label>Case Assistance</label>' in out
    assert '<field>Group_Information__c</field>' in out
    # everything after the last original section is preserved verbatim
    tail = xml[xml.rfind('</layoutSections>') + len('</layoutSections>'):]
    assert out.endswith(tail)
    # every original section label survives
    import re
    for lbl in re.findall(r'<label>(.*?)</label>', xml):
        assert f'<label>{lbl}</label>' in out


# ── add_to_section ────────────────────────────────────────────────────────────

def test_add_to_existing_section_places_inside():
    xml = _load(PRIMARY)
    r = L.add_to_section(xml, 'Case Information',
                         ['Group_Information__c', 'Occurrence_Date__c'], 'Edit')
    out = r['xml']
    ET.fromstring(out)
    ci = out.find('<label>Case Information</label>')
    gi = out.find('<field>Group_Information__c</field>')
    end = out.find('</layoutSections>', ci)
    assert ci < gi < end  # placed within the Case Information section
    assert out.count('</layoutSections>') == xml.count('</layoutSections>')  # no new section


def test_add_to_missing_section_raises():
    with pytest.raises(ValueError):
        L.add_to_section(_load(PRIMARY), 'Nope', ['X__c'], 'Edit')


def test_add_to_section_without_editable_column_raises():
    # 'Custom Links' has only empty <layoutColumns/>.
    with pytest.raises(ValueError):
        L.add_to_section(_load(PRIMARY), 'Custom Links', ['X__c'], 'Edit')


# ── dedup / validation / helpers ──────────────────────────────────────────────

def test_fields_already_on_layout_are_skipped():
    xml = _load(PRIMARY)
    r = L.add_new_section(xml, 'X', ['OwnerId', 'Case.Group_Information__c'], 'Edit')
    assert 'OwnerId' in r['skipped'] and 'Group_Information__c' in r['added']


def test_all_fields_present_raises():
    with pytest.raises(ValueError):
        L.add_new_section(_load(PRIMARY), 'X', ['OwnerId', 'CaseNumber'], 'Edit')


def test_bad_behavior_raises():
    with pytest.raises(ValueError):
        L.add_new_section(_load(PRIMARY), 'X', ['New__c'], 'Bogus')


def test_not_a_layout_raises():
    with pytest.raises(ValueError):
        L.add_new_section('<NotALayout/>', 'X', ['New__c'], 'Edit')


def test_list_sections_flags_editable_columns():
    secs = {s['label']: s['has_editable_column'] for s in L.list_sections(_load(PRIMARY))}
    assert secs['Case Information'] is True
    assert secs['Custom Links'] is False


def test_field_short_strips_object_prefix():
    r = L.add_new_section(_load(PRIMARY), 'X', ['Case.Some_New__c'], 'Edit')
    assert '<field>Some_New__c</field>' in r['xml']
    assert 'Case.Some_New__c' not in r['xml']
