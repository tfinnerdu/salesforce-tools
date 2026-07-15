"""Unit tests for services.cli_script (XML + snippet + zip generation).

Pure/deterministic module — no patching needed. Byte-for-byte artifact
fidelity against the real Conductor package is pinned separately in
tests/characterization/test_cli_artifacts_characterization.py.
"""
import io
import zipfile

import pytest

from services import cli_script as cs


# ── field_meta_xml ────────────────────────────────────────────────────────────

def test_text_external_id_field_xml():
    xml = cs.field_meta_xml({
        'api_name': 'SIS_ID__c', 'label': 'SIS ID', 'type': 'Text',
        'length': 36, 'externalId': True, 'unique': True, 'caseSensitive': False,
        'required': False,
    })
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<CustomField')
    assert '<fullName>SIS_ID__c</fullName>' in xml
    assert '<externalId>true</externalId>' in xml
    assert '<length>36</length>' in xml
    assert '<unique>true</unique>' in xml
    assert '<caseSensitive>false</caseSensitive>' in xml
    assert xml.endswith('</CustomField>\n')
    # externalId comes before label (matches sf retrieve ordering)
    assert xml.index('<externalId>') < xml.index('<label>')


def test_text_without_unique_omits_case_sensitive():
    xml = cs.field_meta_xml({'api_name': 'Note__c', 'label': 'Note', 'type': 'Text', 'length': 100})
    assert '<caseSensitive>' not in xml
    assert '<unique>' not in xml


def test_checkbox_has_default_no_required():
    xml = cs.field_meta_xml({'api_name': 'Active__c', 'label': 'Active', 'type': 'Checkbox',
                             'defaultValue': True})
    assert '<type>Checkbox</type>' in xml
    assert '<defaultValue>true</defaultValue>' in xml
    assert '<required>' not in xml  # checkbox is always valued


def test_number_precision_scale_and_extid():
    xml = cs.field_meta_xml({'api_name': 'Score__c', 'label': 'Score', 'type': 'Number',
                             'precision': 5, 'scale': 2, 'externalId': True, 'unique': True})
    assert '<precision>5</precision>' in xml and '<scale>2</scale>' in xml
    assert '<externalId>true</externalId>' in xml and '<unique>true</unique>' in xml


def test_picklist_active_and_retired_values():
    xml = cs.field_meta_xml({'api_name': 'Type__c', 'label': 'Type', 'type': 'Picklist',
        'picklist': {'restricted': True, 'sorted': False, 'values': [
            {'value': 'MAJ', 'label': 'Major', 'active': True},
            {'value': 'Old', 'label': 'Old', 'active': False},
        ]}})
    assert '<restricted>true</restricted>' in xml
    assert '<value><fullName>MAJ</fullName><default>false</default><label>Major</label></value>' in xml
    assert '<value><fullName>Old</fullName><default>false</default><isActive>false</isActive><label>Old</label></value>' in xml


def test_description_is_xml_escaped():
    xml = cs.field_meta_xml({'api_name': 'X__c', 'label': 'X & <Y>', 'type': 'Text',
                             'description': 'a & b < c'})
    assert '<label>X &amp; &lt;Y&gt;</label>' in xml
    assert '<description>a &amp; b &lt; c</description>' in xml


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        cs.field_meta_xml({'api_name': 'X__c', 'type': 'Location'})


def test_missing_api_name_raises():
    with pytest.raises(ValueError):
        cs.field_meta_xml({'type': 'Text', 'label': 'x'})


# ── permission_set_xml ────────────────────────────────────────────────────────

def test_permission_set_xml_orders_and_escapes():
    xml = cs.permission_set_xml('SF_Tools_Importer', 'SF Tools Importer', [
        {'field': 'Account.SIS_ID__c', 'readable': True, 'editable': False},
        {'field': 'CourseOfferingParticipant.Ethos_Guid__c', 'readable': True, 'editable': True},
    ], description='A & B')
    assert '<label>SF Tools Importer</label>' in xml
    assert '<description>A &amp; B</description>' in xml
    assert '<hasActivationRequired>false</hasActivationRequired>' in xml
    assert ('<fieldPermissions><field>Account.SIS_ID__c</field>'
            '<readable>true</readable><editable>false</editable></fieldPermissions>') in xml
    # input order preserved
    assert xml.index('Account.SIS_ID__c') < xml.index('CourseOfferingParticipant.Ethos_Guid__c')


# ── snippets ──────────────────────────────────────────────────────────────────

def test_retrieve_snippet_has_no_bogus_object_type():
    snip = cs.retrieve_snippet('DoaneUAT')
    assert '-m CustomObject' in snip and '-m PermissionSet' in snip
    # There is no `Object` metadata type; only CustomObject.
    assert '-m Object ' not in snip and not snip.rstrip().endswith('-m Object')


def test_deploy_snippet_powershell_backticks_and_flags():
    fields = [{'object': 'Account', 'api_name': 'SIS_ID__c'},
              {'object': 'Contact', 'api_name': 'Ethos_Guid__c'}]
    dry = cs.deploy_snippet(fields, 'SF_Tools_Importer', 'DoaneUAT', dry_run=True)
    lines = dry.split('\n')
    assert lines[0] == 'sf project deploy start `'
    # every continued line ends with a backtick, with no trailing whitespace after it
    for ln in lines[:-1]:
        assert ln.endswith('`'), ln
        assert ln == ln.rstrip(), f'trailing whitespace after backtick: {ln!r}'
    assert '-m "CustomField:Account.SIS_ID__c" `' in dry
    assert '-m "PermissionSet:SF_Tools_Importer" `' in dry
    assert lines[-1] == '  -o DoaneUAT --dry-run'
    # full deploy drops --dry-run
    full = cs.deploy_snippet(fields, 'SF_Tools_Importer', 'DoaneUAT', dry_run=False)
    assert full.strip().endswith('-o DoaneUAT')
    assert '--dry-run' not in full


def test_assign_snippet_spacing():
    snip = cs.assign_snippet('SF_Tools_Importer', 'DoaneUAT', 'svc.integration@doane.edu')
    assert snip == ('sf org assign permset --name SF_Tools_Importer '
                    '--on-behalf-of svc.integration@doane.edu -o DoaneUAT')


def test_assign_snippet_placeholder_when_no_username():
    assert '<integration-username>' in cs.assign_snippet('PS', 'DoaneUAT', '')


def test_assign_snippets_one_line_per_permset():
    out = cs.assign_snippets([
        {'name': 'SF_Tools_Importer', 'username': 'svc@doane.edu'},
        {'name': 'Case_Assistance_Fields', 'username': '<staff-username>'},
    ], 'DoaneUAT')
    lines = out.split('\n')
    assert len(lines) == 2
    assert lines[0] == 'sf org assign permset --name SF_Tools_Importer --on-behalf-of svc@doane.edu -o DoaneUAT'
    assert 'Case_Assistance_Fields' in lines[1] and '<staff-username>' in lines[1]
    # entries with no name are skipped
    assert cs.assign_snippets([{'name': '', 'username': 'x'}], 'DoaneUAT') == ''


def test_deploy_snippet_includes_extra_permsets():
    fields = [{'object': 'Case', 'api_name': 'X__c'}]
    out = cs.deploy_snippet(fields, 'SF_Tools_Importer', 'DoaneUAT',
                            extra_permset_names=['Case_Assistance_Fields'])
    assert '-m "PermissionSet:SF_Tools_Importer" `' in out
    assert '-m "PermissionSet:Case_Assistance_Fields" `' in out
    # a duplicate name isn't emitted twice
    out2 = cs.deploy_snippet(fields, 'SF_Tools_Importer', 'DoaneUAT',
                             extra_permset_names=['SF_Tools_Importer'])
    assert out2.count('PermissionSet:SF_Tools_Importer') == 1


def test_backup_and_verify_only_for_flips():
    assert cs.backup_snippet([], 'DoaneUAT') == ''
    assert cs.verify_snippet([], 'DoaneUAT') == ''
    flips = [{'object': 'Account', 'api_name': 'SIS_ID__c'},
             {'object': 'Contact', 'api_name': 'Ethos_Guid__c'}]
    backup = cs.backup_snippet(flips, 'DoaneUAT')
    assert '--target-metadata-dir ./_backup' in backup
    assert '-m "CustomField:Account.SIS_ID__c" `' in backup
    verify = cs.verify_snippet(flips, 'DoaneUAT')
    assert "'Account','Contact' | ForEach-Object" in verify
    assert "Where-Object { $_.name -in @('Ethos_Guid__c','SIS_ID__c') }" in verify
    assert 'Select-Object name, externalId, idLookup, unique, length' in verify


def test_command_recipes():
    r = cs.command_recipes('CourseOfferingParticipant', ['Name', 'SIS_ID__c'], 'DoaneUAT')
    assert r['describe'] == 'sf sobject describe --sobject CourseOfferingParticipant -o DoaneUAT'
    assert r['count'] == 'sf data query -o DoaneUAT -q "SELECT COUNT() FROM CourseOfferingParticipant"'
    assert r['query'] == ('sf data query -o DoaneUAT -q "SELECT Id, Name, SIS_ID__c '
                          'FROM CourseOfferingParticipant LIMIT 10"')
    assert r['retrieve_object'] == 'sf project retrieve start -m "CustomObject:CourseOfferingParticipant" -o DoaneUAT'
    assert r['soql'] == 'SELECT Id, Name, SIS_ID__c FROM CourseOfferingParticipant LIMIT 10'


def test_recipe_soql_dedupes_id_and_handles_empty():
    assert cs.recipe_soql('Account', ['Id', 'Name'], 10) == 'SELECT Id, Name FROM Account LIMIT 10'
    assert cs.recipe_soql('Account', [], 10) == 'SELECT Id FROM Account LIMIT 10'
    assert '<Object>' in cs.recipe_soql('', [], 10)


def test_recordtype_snippets():
    assert cs.recordtype_retrieve_snippet('Case.Advisee_Case', 'DoaneUAT') == \
        'sf project retrieve start -m "RecordType:Case.Advisee_Case" -o DoaneUAT'
    assert cs.recordtype_deploy_snippet('Case.Advisee_Case', 'DoaneUAT', dry_run=True) == \
        'sf project deploy start -m "RecordType:Case.Advisee_Case" -o DoaneUAT --dry-run'
    assert '<Object>.<RecordType>' in cs.recordtype_retrieve_snippet('', 'DoaneUAT')


def test_deploy_dir_snippet():
    assert cs.deploy_dir_snippet('DoaneUAT', dry_run=True) == \
        'sf project deploy start --source-dir force-app -o DoaneUAT --dry-run'
    assert cs.deploy_dir_snippet('DoaneUAT', dry_run=False) == \
        'sf project deploy start --source-dir force-app -o DoaneUAT'
    assert '-m ' not in cs.deploy_dir_snippet('DoaneUAT')  # no per-component gotcha


def test_layout_snippets():
    assert cs.layout_retrieve_snippet('Case-Case Layout', 'DoaneUAT') == \
        'sf project retrieve start -m "Layout:Case-Case Layout" -o DoaneUAT'
    assert cs.layout_deploy_snippet('Case-Case Layout', 'DoaneUAT', dry_run=True) == \
        'sf project deploy start -m "Layout:Case-Case Layout" -o DoaneUAT --dry-run'
    assert cs.layout_deploy_snippet('Case-Case Layout', 'DoaneUAT', dry_run=False) == \
        'sf project deploy start -m "Layout:Case-Case Layout" -o DoaneUAT'
    assert '<Object>-<Layout Name>' in cs.layout_retrieve_snippet('', 'DoaneUAT')


def test_login_and_project_snippets():
    login = cs.login_snippet('DoaneUAT', 'https://x--full.sandbox.my.salesforce.com')
    assert login == ('sf org login web --instance-url '
                     'https://x--full.sandbox.my.salesforce.com --alias DoaneUAT')
    proj = cs.project_snippet('doane-sf', 'DoaneUAT', 'C:\\Doane\\Code\\Salesforce-Projects')
    assert 'sf project generate --name doane-sf' in proj
    assert 'cd "C:\\Doane\\Code\\Salesforce-Projects\\doane-sf"' in proj
    assert '--target-org DoaneUAT' in proj


# ── package zip ───────────────────────────────────────────────────────────────

def test_build_package_zip_layout():
    fields = [{'object': 'Account', 'api_name': 'SIS_ID__c', 'label': 'SIS ID',
               'type': 'Text', 'length': 36, 'externalId': True, 'unique': True, 'mode': 'flip'}]
    permset = {'api_name': 'SF_Tools_Importer', 'label': 'SF Tools Importer',
               'field_perms': [{'field': 'Account.SIS_ID__c', 'readable': True, 'editable': True}]}
    data, filename = cs.build_package_zip('doane-sf', fields, permset, 'DoaneUAT')
    assert filename == 'sf-cli-package-doane-sf.zip'
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())
    assert 'force-app/main/default/objects/Account/fields/SIS_ID__c.field-meta.xml' in names
    assert 'force-app/main/default/permissionsets/SF_Tools_Importer.permissionset-meta.xml' in names
    assert 'manifest/package.xml' in names
    assert 'README.txt' in names
    pkg = zf.read('manifest/package.xml').decode()
    assert '<members>Account.SIS_ID__c</members>' in pkg
    assert '<members>SF_Tools_Importer</members>' in pkg


def test_build_package_zip_empty_raises():
    with pytest.raises(ValueError):
        cs.build_package_zip('p', [], None, 'DoaneUAT')


# ── Phase 2: CustomTab + tab-visibility + Profile generators ──────────────────

def test_tab_meta_xml():
    xml = cs.tab_meta_xml('RoomAssignment__c')
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<CustomTab')
    assert '<customObject>true</customObject>' in xml
    assert '<motif>' in xml
    assert xml.endswith('</CustomTab>\n')


def test_tab_meta_xml_requires_object():
    with pytest.raises(ValueError):
        cs.tab_meta_xml('')


def test_permission_set_xml_with_tab_settings():
    xml = cs.permission_set_xml(
        'RA_Access', 'RA Access',
        [{'field': 'RoomAssignment__c.Room__c', 'readable': True, 'editable': True}],
        tab_settings=[{'tab': 'RoomAssignment__c', 'visibility': 'Visible'}])
    assert '<tabSettings><tab>RoomAssignment__c</tab><visibility>Visible</visibility></tabSettings>' in xml


def test_permission_set_xml_no_tab_settings_by_default():
    xml = cs.permission_set_xml('P', 'P',
                                [{'field': 'A.B__c', 'readable': True, 'editable': False}])
    assert '<tabSettings>' not in xml   # additive — unchanged unless requested


def test_profile_xml_object_and_field_grants():
    xml = cs.profile_xml(
        'System Administrator',
        object_perms=cs.object_perms_for(['RoomAssignment__c'], True),
        field_perms=[{'field': 'RoomAssignment__c.Room__c', 'readable': True, 'editable': True}])
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<Profile')
    assert '<object>RoomAssignment__c</object>' in xml
    assert '<field>RoomAssignment__c.Room__c</field>' in xml
    # retrieve order: fieldPermissions before objectPermissions
    assert xml.index('<fieldPermissions>') < xml.index('<objectPermissions>')
    assert xml.endswith('</Profile>\n')


def test_profile_xml_maps_tab_visibility_enum():
    # Permission-set "Visible" maps to a profile's "DefaultOn".
    xml = cs.profile_xml('Standard User',
                         tab_settings=[{'tab': 'RoomAssignment__c', 'visibility': 'Visible'}])
    assert '<tabVisibilities><tab>RoomAssignment__c</tab><visibility>DefaultOn</visibility></tabVisibilities>' in xml


def test_profile_xml_requires_api_name():
    with pytest.raises(ValueError):
        cs.profile_xml('')


def test_package_xml_with_tabs_and_profiles():
    pkg = cs.package_xml([], tab_names=['RoomAssignment__c'],
                         profile_names=['System Administrator'])
    assert '<name>CustomTab</name>' in pkg
    assert '<name>Profile</name>' in pkg
    assert '<members>RoomAssignment__c</members>' in pkg
    assert '<members>System Administrator</members>' in pkg


def test_deploy_snippet_orders_tab_and_profile():
    s = cs.deploy_snippet(
        [{'object': 'Foo__c', 'api_name': 'Bar__c'}], 'PS', 'UAT',
        object_names=['Foo__c'], tab_names=['Foo__c'], profile_names=['Admin'])
    # object -> field -> tab -> permset -> profile
    assert s.index('CustomObject:Foo__c') < s.index('CustomField:Foo__c.Bar__c')
    assert s.index('CustomField:Foo__c.Bar__c') < s.index('CustomTab:Foo__c')
    assert s.index('PermissionSet:PS') < s.index('Profile:Admin')


def test_build_package_zip_with_tab_and_profile():
    fields = [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}]
    tabs = [{'object': 'Foo__c'}]
    profiles = [{'api_name': 'System Administrator',
                 'object_perms': cs.object_perms_for(['Foo__c'], True),
                 'field_perms': [{'field': 'Foo__c.Bar__c', 'readable': True, 'editable': True}]}]
    data, _ = cs.build_package_zip('p', fields, None, 'UAT', tabs=tabs, profiles=profiles)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert 'force-app/main/default/tabs/Foo__c.tab-meta.xml' in names
        assert 'force-app/main/default/profiles/System Administrator.profile-meta.xml' in names
        pkg = zf.read('manifest/package.xml').decode()
        prof = zf.read('force-app/main/default/profiles/System Administrator.profile-meta.xml').decode()
    assert '<name>CustomTab</name>' in pkg and '<name>Profile</name>' in pkg
    assert '<object>Foo__c</object>' in prof


def test_build_package_zip_profile_with_no_grants_is_dropped():
    # A profile file that grants nothing is not written (and can't be the only content).
    with pytest.raises(ValueError):
        cs.build_package_zip('p', [], None, 'UAT',
                             profiles=[{'api_name': 'Empty'}])


# ── build_package_zip: base_path threading (config hygiene) ──────────────────

def test_readme_uses_configured_base_path_when_given():
    fields = [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}]
    data, _ = cs.build_package_zip('proj', fields, None, 'UAT',
                                   base_path='C:\\Other\\Projects')
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        readme = zf.read('README.txt').decode()
    assert 'C:\\Other\\Projects\\proj' in readme
    assert 'C:\\Doane\\Code\\Salesforce-Projects' not in readme


def test_readme_falls_back_to_default_base_path_when_not_given():
    fields = [{'object': 'Foo__c', 'api_name': 'Bar__c', 'label': 'Bar', 'type': 'Text'}]
    data, _ = cs.build_package_zip('proj', fields, None, 'UAT')
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        readme = zf.read('README.txt').decode()
    assert 'C:\\Doane\\Code\\Salesforce-Projects\\proj' in readme


def test_base_project_path_with_and_without_override():
    assert cs.base_project_path('proj') == 'C:\\Doane\\Code\\Salesforce-Projects\\proj'
    assert cs.base_project_path('proj', 'C:\\Other') == 'C:\\Other\\proj'
