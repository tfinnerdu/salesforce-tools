"""
Characterization tests — CLI tab generated artifacts.

Pins the CLI generator's output against known-good artifacts the team actually
deployed (the Conductor EDA->EDF field package and the field guide's deploy
command). These are not mocks: they hardcode what correct output looks like and
fail if the generator, the field-spec shape, or the command grammar drifts.

If one fails due to an intentional change, update the hardcoded value AND note
what changed and why — the test is a changelog for these invariants.

What each pins:
- Text external-ID CustomField XML  -> exact bytes of a real field-meta.xml
- PermissionSet XML                 -> exact bytes of the real permission set
- Deploy command                    -> exact PowerShell backtick command shape
- Retrieve command                  -> must NOT emit a bogus `-m Object` type
"""
from services import cli_script as cs


# Known-good: CourseOfferingParticipant.Ethos_Guid__c.field-meta.xml as shipped
# in the Conductor migration package (Text 36, External ID, unique, CI).
KNOWN_FIELD_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    '    <fullName>Ethos_Guid__c</fullName>\n'
    '    <description>Guid from the SID platform. Upsert match key for section-registration sync.</description>\n'
    '    <externalId>true</externalId>\n'
    '    <label>Ethos Guid</label>\n'
    '    <length>36</length>\n'
    '    <required>false</required>\n'
    '    <trackTrending>false</trackTrending>\n'
    '    <type>Text</type>\n'
    '    <unique>true</unique>\n'
    '    <caseSensitive>false</caseSensitive>\n'
    '</CustomField>\n'
)


def test_text_external_id_field_matches_conductor_artifact():
    got = cs.field_meta_xml({
        'api_name': 'Ethos_Guid__c',
        'label': 'Ethos Guid',
        'type': 'Text',
        'description': 'Guid from the SID platform. Upsert match key for section-registration sync.',
        'externalId': True,
        'length': 36,
        'required': False,
        'unique': True,
        'caseSensitive': False,
    })
    assert got == KNOWN_FIELD_XML, (
        'Generated field-meta.xml diverged from the known-good Conductor artifact. '
        'The CLI tab would produce metadata that no longer matches hand-authored fields. '
        'Verify the change is intentional before updating this snapshot.'
    )


# Known-good: the real Conductor_Integration_Access permission set.
KNOWN_PERMSET_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    '    <label>Conductor Integration Access</label>\n'
    '    <description>Field access for the Conductor integration user across the EDA-&gt;EDF migration. '
    'Edit on written fields (external ids + Type__c), read on match fields. Assign to the integration user. '
    'If that user is NOT a System Admin, extend with the other written fields listed in README.</description>\n'
    '    <hasActivationRequired>false</hasActivationRequired>\n'
    '    <fieldPermissions><field>CourseOfferingParticipant.Ethos_Guid__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>CourseOfferingParticipant.SIS_ID__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>CourseOfferingPtcpResult.Ethos_Guid__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>CourseOfferingPtcpResult.SIS_ID__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>Student_Advisement__c.Ethos_Guid__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>Student_Advisement__c.SIS_ID__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>Student_Advisement__c.Type__c</field><readable>true</readable><editable>true</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>CourseOffering.Ethos_Guid__c</field><readable>true</readable><editable>false</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>Contact.Ethos_Guid__c</field><readable>true</readable><editable>false</editable></fieldPermissions>\n'
    '    <fieldPermissions><field>Account.SIS_ID__c</field><readable>true</readable><editable>false</editable></fieldPermissions>\n'
    '</PermissionSet>\n'
)


def test_permission_set_matches_conductor_artifact():
    edit = ['CourseOfferingParticipant.Ethos_Guid__c', 'CourseOfferingParticipant.SIS_ID__c',
            'CourseOfferingPtcpResult.Ethos_Guid__c', 'CourseOfferingPtcpResult.SIS_ID__c',
            'Student_Advisement__c.Ethos_Guid__c', 'Student_Advisement__c.SIS_ID__c',
            'Student_Advisement__c.Type__c']
    read = ['CourseOffering.Ethos_Guid__c', 'Contact.Ethos_Guid__c', 'Account.SIS_ID__c']
    fps = ([{'field': f, 'readable': True, 'editable': True} for f in edit] +
           [{'field': f, 'readable': True, 'editable': False} for f in read])
    desc = ('Field access for the Conductor integration user across the EDA->EDF migration. '
            'Edit on written fields (external ids + Type__c), read on match fields. Assign to the integration user. '
            'If that user is NOT a System Admin, extend with the other written fields listed in README.')
    got = cs.permission_set_xml('Conductor_Integration_Access', 'Conductor Integration Access', fps, desc)
    assert got == KNOWN_PERMSET_XML, (
        'Generated permission set diverged from the known-good Conductor artifact. '
        'Verify the change is intentional before updating this snapshot.'
    )


# Known-good: the deploy command from the field guide / Step 9 spec (corrected
# spacing), backtick-continued for PowerShell.
KNOWN_DEPLOY = (
    'sf project deploy start `\n'
    '  -m "CustomField:CourseOfferingParticipant.Ethos_Guid__c" `\n'
    '  -m "CustomField:CourseOfferingParticipant.SIS_ID__c" `\n'
    '  -m "CustomField:CourseOfferingPtcpResult.Ethos_Guid__c" `\n'
    '  -m "CustomField:CourseOfferingPtcpResult.SIS_ID__c" `\n'
    '  -m "CustomField:Student_Advisement__c.Ethos_Guid__c" `\n'
    '  -m "CustomField:Student_Advisement__c.SIS_ID__c" `\n'
    '  -m "CustomField:Student_Advisement__c.Type__c" `\n'
    '  -m "PermissionSet:SF_Tools_Importer" `\n'
    '  -o DoaneUAT'
)


def test_deploy_command_matches_field_guide_shape():
    fields = [{'object': o, 'api_name': f} for o, f in [
        ('CourseOfferingParticipant', 'Ethos_Guid__c'),
        ('CourseOfferingParticipant', 'SIS_ID__c'),
        ('CourseOfferingPtcpResult', 'Ethos_Guid__c'),
        ('CourseOfferingPtcpResult', 'SIS_ID__c'),
        ('Student_Advisement__c', 'Ethos_Guid__c'),
        ('Student_Advisement__c', 'SIS_ID__c'),
        ('Student_Advisement__c', 'Type__c'),
    ]]
    got = cs.deploy_snippet(fields, 'SF_Tools_Importer', 'DoaneUAT', dry_run=False)
    assert got == KNOWN_DEPLOY, (
        'Deploy command grammar drifted. PowerShell needs a trailing backtick per line '
        '(never a backslash) and `-o <alias>` on its own final line. '
        'Verify the change is intentional before updating this snapshot.'
    )


def test_retrieve_command_has_no_object_metadata_type():
    # `Object` is not a Metadata API type; the correct pull is CustomObject.
    snip = cs.retrieve_snippet('DoaneUAT')
    for ln in snip.split('\n'):
        assert ln.strip() != '-m Object', 'Emitted a bogus `-m Object` metadata type'
    assert '-m CustomObject' in snip and '-m PermissionSet' in snip
