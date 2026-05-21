"""Org-to-org metadata diff.

Schema > Org Schema Diff compares *fields* on specific objects. This module
extends the comparison to deployable metadata components — Apex classes, Apex
triggers, flows, validation rules, and custom objects — the things most likely
to drift between a sandbox and production during the Ed Cloud migration.

For each metadata type a component is reduced to a name and a fingerprint. The
diff reports components present in only one org (left-only / right-only) and
components present in both but configured differently (modified).

Real orgs are queried via the Tooling / Data API. In mock mode a seeded
catalog is used; the 'prod' variant deliberately lags the dev sandbox so the
diff is demonstrable without two live orgs.
"""
import logging
from datetime import datetime, timezone

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

# Ordered — drives both the API response and the type picker on the page.
METADATA_TYPES = [
    ('apex_classes', 'Apex Classes'),
    ('apex_triggers', 'Apex Triggers'),
    ('flows', 'Flows'),
    ('validation_rules', 'Validation Rules'),
    ('custom_objects', 'Custom Objects'),
]
_TYPE_KEYS = {k for k, _ in METADATA_TYPES}


# ── Real-org fetchers ─────────────────────────────────────────────────────────
# Each returns {component_name: {'fingerprint': str, 'detail': str}}.

def _tooling_query_all(sf, soql: str) -> list:
    """Run a Tooling API query, following nextRecordsUrl for the full set.

    sf.restful() returns only the first batch (max 2000 records) — a large org
    would otherwise lose components past that cap from the diff.
    """
    res = sf.restful('tooling/query/', params={'q': soql})
    records = list(res.get('records', []))
    next_url = res.get('nextRecordsUrl')
    while next_url:
        # nextRecordsUrl is rooted at /services/data/vXX.X/; restful() expects
        # a path relative to that version segment.
        rel = next_url.split('/services/data/', 1)[-1].split('/', 1)[-1]
        res = sf.restful(rel)
        records.extend(res.get('records', []))
        next_url = res.get('nextRecordsUrl')
    return records


def _real_apex_classes(sf) -> dict:
    soql = ("SELECT Name, ApiVersion, LengthWithoutComments, Status "
            "FROM ApexClass WHERE NamespacePrefix = null ORDER BY Name")
    out = {}
    for r in _tooling_query_all(sf, soql):
        name = r.get('Name')
        if not name:
            continue
        api = r.get('ApiVersion', '')
        length = r.get('LengthWithoutComments', 0) or 0
        status = r.get('Status', '') or ''
        out[name] = {
            'fingerprint': f'v{api}|{length}|{status}',
            'detail': f'API {api}, {length} chars, {status}',
        }
    return out


def _real_apex_triggers(sf) -> dict:
    soql = ("SELECT Name, Status, ApiVersion, LengthWithoutComments, "
            "EntityDefinition.QualifiedApiName "
            "FROM ApexTrigger WHERE NamespacePrefix = null ORDER BY Name")
    out = {}
    for r in _tooling_query_all(sf, soql):
        name = r.get('Name')
        if not name:
            continue
        ent = r.get('EntityDefinition') or {}
        obj = ent.get('QualifiedApiName', '') if isinstance(ent, dict) else ''
        status = r.get('Status', '') or ''
        length = r.get('LengthWithoutComments', 0) or 0
        out[name] = {
            'fingerprint': f'{obj}|{status}|{length}',
            'detail': f'{obj} · {status} · {length} chars',
        }
    return out


def _real_flows(sf) -> dict:
    soql = ("SELECT ApiName, Label, ProcessType, IsActive "
            "FROM FlowDefinitionView ORDER BY ApiName")
    res = sf.query_all(soql)
    out = {}
    for r in res.get('records', []):
        name = r.get('ApiName')
        if not name:
            continue
        ptype = r.get('ProcessType', '') or ''
        status = 'Active' if r.get('IsActive') else 'Inactive'
        out[name] = {
            'fingerprint': f'{ptype}|{status}',
            'detail': f'{ptype} · {status}',
        }
    return out


def _real_validation_rules(sf) -> dict:
    # No ORDER BY on the cross-entity relationship — it triggers UNKNOWN_EXCEPTION.
    soql = ("SELECT ValidationName, Active, EntityDefinition.QualifiedApiName "
            "FROM ValidationRule")
    out = {}
    for r in _tooling_query_all(sf, soql):
        rule = r.get('ValidationName')
        if not rule:
            continue
        ent = r.get('EntityDefinition') or {}
        obj = ent.get('QualifiedApiName', '') if isinstance(ent, dict) else ''
        status = 'Active' if r.get('Active') else 'Inactive'
        out[f'{obj}.{rule}'] = {
            'fingerprint': status,
            'detail': f'{obj} · {status}',
        }
    return out


def _real_custom_objects(sf) -> dict:
    # EntityDefinition is a special Tooling API entity: it does NOT support
    # queryMore(), so it cannot be paginated. A LIMIT (max 2000) is mandatory
    # and the result is hard-capped there — _tooling_query_all would not help.
    # An org with >2000 sharing-modelled entities is at the platform ceiling.
    soql = ("SELECT QualifiedApiName, Label, InternalSharingModel "
            "FROM EntityDefinition WHERE InternalSharingModel != null LIMIT 2000")
    res = sf.restful('tooling/query/', params={'q': soql})
    out = {}
    for r in res.get('records', []):
        name = r.get('QualifiedApiName', '')
        if not name.endswith('__c'):
            continue
        label = r.get('Label', '') or name
        sharing = r.get('InternalSharingModel', '') or ''
        out[name] = {
            'fingerprint': sharing,
            'detail': f'{label} · {sharing}',
        }
    return out


_REAL_FETCHERS = {
    'apex_classes': _real_apex_classes,
    'apex_triggers': _real_apex_triggers,
    'flows': _real_flows,
    'validation_rules': _real_validation_rules,
    'custom_objects': _real_custom_objects,
}


# ── Mock catalog ──────────────────────────────────────────────────────────────
# The dev-sandbox baseline. Each entry is name -> (fingerprint, detail).

_MOCK_BASE = {
    'apex_classes': {
        'StudentSyncService':      ('v59.0|4820|Active', 'API 59.0, 4820 chars, Active'),
        'AccountTriggerHandler':   ('v59.0|2110|Active', 'API 59.0, 2110 chars, Active'),
        'EthosIntegrationUtil':    ('v59.0|3640|Active', 'API 59.0, 3640 chars, Active'),
        'ContactPointService':     ('v58.0|1290|Active', 'API 58.0, 1290 chars, Active'),
        'MigrationBatchScheduler': ('v59.0|980|Active',  'API 59.0, 980 chars, Active'),
    },
    'apex_triggers': {
        'AccountTrigger':           ('Account|Active|1840',            'Account · Active · 1840 chars'),
        'ContactPointEmailTrigger': ('ContactPointEmail|Active|620',   'ContactPointEmail · Active · 620 chars'),
        'IndividualTrigger':        ('Individual|Inactive|410',        'Individual · Inactive · 410 chars'),
    },
    'flows': {
        'Student_Update_Handler':      ('AutoLaunchedFlow|Active',   'AutoLaunchedFlow · Active'),
        'Migration_Complete_Notifier': ('AutoLaunchedFlow|Active',   'AutoLaunchedFlow · Active'),
        'ContactPoint_Dedupe':         ('Workflow|Inactive',        'Workflow · Inactive'),
    },
    'validation_rules': {
        'Account.Require_SIS_ID':                         ('Active',   'Account · Active'),
        'Account.Valid_Ethos_Guid_Format':                ('Active',   'Account · Active'),
        'ContactPointEmail.ContactPoint_Parent_Required': ('Active',   'ContactPointEmail · Active'),
        'Contact.Legacy_EDA_Block':                       ('Inactive', 'Contact · Inactive'),
    },
    'custom_objects': {
        'Migration_Batch__c':   ('Private', 'Migration Batch · Private'),
        'Crosswalk_Mapping__c': ('Read',    'Crosswalk Mapping · Read'),
        'Sync_Log__c':          ('Private', 'Sync Log · Private'),
    },
}

# How 'prod' lags the dev sandbox, so the mock diff is demonstrable.
_MOCK_PROD_MISSING = {
    'apex_classes': ['MigrationBatchScheduler'],
    'flows': ['Migration_Complete_Notifier'],
    'validation_rules': ['Account.Valid_Ethos_Guid_Format'],
    'custom_objects': ['Sync_Log__c'],
}
_MOCK_PROD_MODIFIED = {
    'apex_classes': {'StudentSyncService': ('v58.0|4120|Active', 'API 58.0, 4120 chars, Active')},
    'flows': {'Student_Update_Handler': ('AutoLaunchedFlow|Inactive', 'AutoLaunchedFlow · Inactive')},
}
_MOCK_PROD_EXTRA = {
    'apex_classes': {'LegacyEDAContactSync': ('v52.0|2200|Inactive', 'API 52.0, 2200 chars, Inactive')},
}


def _mock_components(meta_type: str, org: str) -> dict:
    """Return the seeded component map for a metadata type and org."""
    base = {n: {'fingerprint': fp, 'detail': dt}
            for n, (fp, dt) in _MOCK_BASE[meta_type].items()}
    if (org or '').lower() not in ('prod', 'production'):
        return base
    result = dict(base)
    for name in _MOCK_PROD_MISSING.get(meta_type, []):
        result.pop(name, None)
    for name, (fp, dt) in _MOCK_PROD_MODIFIED.get(meta_type, {}).items():
        if name in result:
            result[name] = {'fingerprint': fp, 'detail': dt}
    for name, (fp, dt) in _MOCK_PROD_EXTRA.get(meta_type, {}).items():
        result[name] = {'fingerprint': fp, 'detail': dt}
    return result


# ── Diff ──────────────────────────────────────────────────────────────────────

def _fetch(meta_type: str, sf, org: str) -> dict:
    if Config.SF_MOCK:
        return _mock_components(meta_type, org)
    return _REAL_FETCHERS[meta_type](sf)


def diff_components(left: dict, right: dict) -> dict:
    """Compare two name->{fingerprint,detail} maps and return a structured diff."""
    left_names = set(left)
    right_names = set(right)
    shared = left_names & right_names

    left_only = [{'name': n, 'detail': left[n]['detail']}
                 for n in sorted(left_names - right_names)]
    right_only = [{'name': n, 'detail': right[n]['detail']}
                  for n in sorted(right_names - left_names)]
    modified = [
        {'name': n,
         'left_detail': left[n]['detail'],
         'right_detail': right[n]['detail']}
        for n in sorted(shared)
        if left[n]['fingerprint'] != right[n]['fingerprint']
    ]
    return {
        'left_only': left_only,
        'right_only': right_only,
        'modified': modified,
        'identical': len(shared) - len(modified),
        'left_total': len(left),
        'right_total': len(right),
        'difference_count': len(left_only) + len(right_only) + len(modified),
    }


def run_metadata_diff(left_org: str, right_org: str, types=None) -> dict:
    """Diff deployable metadata between two orgs.

    ``types`` is an optional list of metadata-type keys (see METADATA_TYPES);
    when omitted or empty, every type is compared.
    """
    requested = [t for t in (types or []) if t in _TYPE_KEYS]
    selected = requested if requested else list(_TYPE_KEYS)

    sf_left = get_sf(left_org)
    sf_right = get_sf(right_org)
    labels = dict(METADATA_TYPES)

    results = []
    total_diffs = 0
    for key, _label in METADATA_TYPES:
        if key not in selected:
            continue
        try:
            diff = diff_components(
                _fetch(key, sf_left, left_org),
                _fetch(key, sf_right, right_org),
            )
        except Exception as exc:
            logger.warning('metadata diff failed for %s: %s', key, exc)
            diff = {'error': str(exc), 'difference_count': 0}
        diff['type'] = key
        diff['label'] = labels[key]
        results.append(diff)
        total_diffs += diff.get('difference_count', 0)

    return {
        'left_org': left_org,
        'right_org': right_org,
        'types': results,
        'total_differences': total_diffs,
        'run_at': datetime.now(timezone.utc).isoformat(),
    }
