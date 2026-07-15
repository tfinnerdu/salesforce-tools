"""Unit tests for services.cli_fls (visibility clone).

No live Salesforce: a MagicMock double supplies FieldPermissions query results.
"""
from unittest.mock import MagicMock, patch

from services import cli_fls


def _sf(records):
    sf = MagicMock()
    sf.query_all.return_value = {'records': records}
    return sf


_RECORDS = [
    {'Field': 'Case.X__c', 'PermissionsRead': True, 'PermissionsEdit': True,
     'Parent': {'Label': 'Admin', 'IsOwnedByProfile': True,
                'Profile': {'Name': 'System Administrator'}}},
    {'Field': 'Case.X__c', 'PermissionsRead': True, 'PermissionsEdit': False,
     'Parent': {'Label': 'Case Team PS', 'IsOwnedByProfile': False, 'Profile': None}},
]


def test_read_field_fls_shapes_parents_and_summary():
    out = cli_fls.read_field_fls_from(_sf(_RECORDS), 'Case', 'X__c')
    assert out['field'] == 'Case.X__c'
    names = {p['name']: p for p in out['parents']}
    assert names['System Administrator']['type'] == 'Profile'
    assert names['System Administrator']['edit'] is True
    assert names['Case Team PS']['type'] == 'PermissionSet'
    assert names['Case Team PS']['edit'] is False
    s = out['summary']
    assert s['read_count'] == 2 and s['edit_count'] == 1
    assert s['any_edit'] is True and s['suggested_editable'] is True
    assert s['read_profiles'] == ['System Administrator']


def test_read_field_fls_qualifies_bare_field_name():
    sf = _sf([])
    cli_fls.read_field_fls_from(sf, 'Case', 'X__c')
    soql = sf.query_all.call_args[0][0]
    assert "SobjectType = 'Case'" in soql
    assert "Field = 'Case.X__c'" in soql  # bare name qualified with the object


def test_read_field_fls_escapes_soql():
    sf = _sf([])
    cli_fls.read_field_fls_from(sf, "Ca'se", "X__c")
    soql = sf.query_all.call_args[0][0]
    assert "Ca\\'se" in soql  # single quote escaped, not breaking the literal


def test_read_field_fls_no_access_suggests_read_only():
    out = cli_fls.read_field_fls_from(_sf([]), 'Case', 'X__c')
    assert out['summary']['any_read'] is False
    assert out['summary']['suggested_editable'] is False


def test_read_field_fls_wrapper_uses_get_sf():
    sf = _sf(_RECORDS)
    with patch.object(cli_fls, 'get_sf', return_value=sf) as gs:
        cli_fls.read_field_fls('eda', 'Case', 'X__c')
    gs.assert_called_once_with('eda')


def test_read_field_fls_emits_audit_event():
    # This reads which profiles/permission sets can see a field across the
    # whole org -- a genuine security-posture export, so every call must be
    # audited (see services/audit.py).
    sf = _sf(_RECORDS)
    with patch.object(cli_fls, 'get_sf', return_value=sf), \
            patch('services.cli_fls.audit.emit') as emit:
        cli_fls.read_field_fls('eda', 'Case', 'X__c')
    emit.assert_called_once()
    args, kwargs = emit.call_args
    assert args[0] == 'FLS_READ'
    assert args[1] == 'sf_field_permissions'
    assert args[2] == 'eda:Case.X__c'
    assert args[3] == 'success'


def test_human_field_perms():
    fields = [{'object': 'Case', 'api_name': 'A__c'}, {'object': 'Case', 'api_name': 'B__c'}]
    edit = cli_fls.human_field_perms(fields, True)
    assert edit == [
        {'field': 'Case.A__c', 'readable': True, 'editable': True},
        {'field': 'Case.B__c', 'readable': True, 'editable': True},
    ]
    read_only = cli_fls.human_field_perms(fields, False)
    assert all(p['editable'] is False and p['readable'] is True for p in read_only)
