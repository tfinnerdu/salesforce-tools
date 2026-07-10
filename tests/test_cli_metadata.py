"""Unit tests for services.cli_metadata (describe-driven object/field lists).

No live Salesforce: a MagicMock double supplies the REST describe payloads.
The *_from helpers take an injected client; the thin wrappers resolve it via
get_sf, which we patch.
"""
from unittest.mock import MagicMock, patch

from services import cli_metadata


_SOBJECTS = {
    'sobjects': [
        {'name': 'Account', 'label': 'Account', 'custom': False, 'queryable': True},
        {'name': 'CourseOfferingParticipant', 'label': 'Course Offering Participant',
         'custom': False, 'queryable': True},
        {'name': 'Student_Advisement__c', 'label': 'Student Advisement',
         'custom': True, 'queryable': True},
        {'name': None},  # malformed entry is dropped
    ]
}

_DESCRIBE = {
    'name': 'CourseOfferingParticipant',
    'label': 'Course Offering Participant',
    'custom': False,
    'fields': [
        {'name': 'Id', 'label': 'Record ID', 'type': 'id', 'nillable': False,
         'custom': False, 'externalId': False, 'idLookup': True, 'unique': False},
        {'name': 'Ethos_Guid__c', 'label': 'Ethos Guid', 'type': 'string',
         'length': 36, 'nillable': True, 'custom': True, 'externalId': True,
         'idLookup': True, 'unique': True, 'picklistValues': []},
        {'name': 'ParticipationStatus', 'label': 'Status', 'type': 'picklist',
         'nillable': True, 'custom': False,
         'picklistValues': [{'value': 'Enrolled', 'label': 'Enrolled', 'active': True},
                            {'value': 'Dropped', 'label': 'Dropped', 'active': False}]},
    ],
}


def _sf(payload_map):
    sf = MagicMock()
    sf.restful.side_effect = lambda path, *a, **k: payload_map.get(path, {})
    return sf


# ── list_objects ──────────────────────────────────────────────────────────────

def test_list_objects_from_shapes_and_sorts():
    sf = _sf({'sobjects': _SOBJECTS})
    objs = cli_metadata.list_objects_from(sf)
    names = [o['name'] for o in objs]
    assert names == sorted(names, key=str.lower)
    assert 'Account' in names
    assert None not in names  # malformed dropped
    acct = next(o for o in objs if o['name'] == 'Account')
    assert acct['custom'] is False and acct['queryable'] is True


def test_list_objects_wrapper_uses_get_sf():
    sf = _sf({'sobjects': _SOBJECTS})
    with patch.object(cli_metadata, 'get_sf', return_value=sf) as gs:
        objs = cli_metadata.list_objects('dev')
    gs.assert_called_once_with('dev')
    assert any(o['name'] == 'Student_Advisement__c' and o['custom'] for o in objs)


# ── describe_fields ───────────────────────────────────────────────────────────

def test_describe_fields_from_returns_expected_shape():
    sf = _sf({'sobjects/CourseOfferingParticipant/describe': _DESCRIBE})
    out = cli_metadata.describe_fields_from(sf, 'CourseOfferingParticipant')
    assert out['object'] == 'CourseOfferingParticipant'
    fields = {f['name']: f for f in out['fields']}
    ethos = fields['Ethos_Guid__c']
    assert ethos['externalId'] is True and ethos['unique'] is True and ethos['length'] == 36
    # picklist values carried through with active flags
    status = fields['ParticipationStatus']
    assert {'Enrolled', 'Dropped'} == {p['value'] for p in status['picklistValues']}
    assert any(p['active'] is False for p in status['picklistValues'])


def test_describe_fields_wrapper_uses_get_sf():
    sf = _sf({'sobjects/Account/describe': {'name': 'Account', 'fields': []}})
    with patch.object(cli_metadata, 'get_sf', return_value=sf) as gs:
        out = cli_metadata.describe_fields('sandbox', 'Account')
    gs.assert_called_once_with('sandbox')
    assert out['object'] == 'Account' and out['fields'] == []
