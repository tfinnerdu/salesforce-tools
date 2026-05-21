"""Data Tune — bulk data standardization (the DemandTools 'Tune' equivalent).

Applies deterministic text-normalization rules (proper case, phone formatting,
whitespace trim, state abbreviation, etc.) to Salesforce fields in bulk.
Clean, consistent data fails fewer validation rules on import.
"""
import logging
import re

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)

_PREVIEW_SAMPLE = 200
_MAX_ROWS = 10_000

US_STATES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI',
    'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX',
    'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA',
    'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
    'district of columbia': 'DC',
}


# ── Standardization rules ─────────────────────────────────────────────────────

def _trim(v: str) -> str:
    """Collapse internal whitespace runs and strip the ends."""
    return ' '.join(v.split())


def _lower(v: str) -> str:
    return v.lower()


def _upper(v: str) -> str:
    return v.upper()


def _lowercase_email(v: str) -> str:
    """Trim and lowercase — email addresses are case-insensitive."""
    return v.strip().lower()


def _title_case(v: str) -> str:
    """Simple title case — capitalize the first letter of every space-delimited word."""
    return ' '.join(w[:1].upper() + w[1:].lower() if w else w for w in v.split())


def _proper_case(v: str) -> str:
    """Name-aware proper case: handles hyphens, apostrophes, and the Mc prefix.

    Limitation: does not special-case 'Mac' (would mis-correct names like
    'Mack'); does not handle Roman-numeral suffixes.
    """
    out = v.lower()
    # Capitalize the first letter of each part (start, or after space/hyphen/apostrophe)
    out = re.sub(r"(^|[\s\-'])([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    # Mc prefix: "Mcdonald" -> "McDonald"
    out = re.sub(r"\bMc([a-z])", lambda m: 'Mc' + m.group(1).upper(), out)
    return out


def _phone_us(v: str) -> str:
    """Format a US phone number as (NPA) NXX-XXXX. Left unchanged if not 10 digits."""
    digits = re.sub(r'\D', '', v)
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    if len(digits) == 10:
        return f'({digits[0:3]}) {digits[3:6]}-{digits[6:10]}'
    return v  # cannot safely normalize — leave as-is


def _state_abbrev(v: str) -> str:
    """Convert a full US state name to its 2-letter postal code."""
    return US_STATES.get(v.strip().lower(), v)


# name -> (human label, function)
RULES = {
    'trim':            ('Trim whitespace',            _trim),
    'proper_case':     ('Proper case (name-aware)',   _proper_case),
    'title_case':      ('Title case',                 _title_case),
    'upper':           ('UPPERCASE',                  _upper),
    'lower':           ('lowercase',                  _lower),
    'lowercase_email': ('Lowercase email',            _lowercase_email),
    'phone_us':        ('US phone format',            _phone_us),
    'state_abbrev':    ('State name -> abbreviation', _state_abbrev),
}


def list_rules() -> list:
    """Return the available standardization rules for the UI."""
    return [{'name': k, 'label': v[0]} for k, v in RULES.items()]


def apply_rules(value, rule_names: list) -> str:
    """Apply an ordered list of rule names to a single value."""
    if value is None:
        return value
    result = str(value)
    for rn in rule_names:
        rule = RULES.get(rn)
        if rule:
            result = rule[1](result)
    return result


def _transform_record(record: dict, field_rules: dict) -> list:
    """Return [{field, before, after}] for every field whose value changed."""
    changes = []
    for field, rules in field_rules.items():
        before = record.get(field)
        if before is None or before == '':
            continue
        after = apply_rules(before, rules)
        if str(before) != str(after):
            changes.append({'field': field, 'before': before, 'after': after})
    return changes


# ── Preview / Apply ───────────────────────────────────────────────────────────

def preview_tune(org: str, object_name: str, where_clause: str, field_rules: dict) -> dict:
    """Preview standardization on a sample — shows before/after, writes nothing."""
    if not field_rules:
        raise ValueError('At least one field with rules is required')
    sf = get_sf(org)
    fields = list(field_rules.keys())
    field_list = ', '.join(['Id'] + fields)
    soql = (f"SELECT {field_list} FROM {object_name} "
            f"WHERE {where_clause} LIMIT {_PREVIEW_SAMPLE}")
    result = sf.query(soql)
    records = result.get('records', [])

    total = len(records)
    try:
        cnt = sf.query(f"SELECT COUNT() FROM {object_name} WHERE {where_clause}")
        total = cnt.get('totalSize', len(records))
    except Exception:
        pass

    changed = []
    for r in records:
        ch = _transform_record(r, field_rules)
        if ch:
            changed.append({'id': r.get('Id'), 'changes': ch})

    return {
        'object_name': object_name,
        'sample_size': len(records),
        'total_matching': total,
        'changed_in_sample': len(changed),
        'changed': changed,
    }


def apply_tune(org: str, object_name: str, where_clause: str, field_rules: dict,
               bypass_triggers: bool = False) -> dict:
    """Apply standardization to all matching records via the Bulk API."""
    if not field_rules:
        raise ValueError('At least one field with rules is required')
    sf = get_sf(org)
    fields = list(field_rules.keys())
    field_list = ', '.join(['Id'] + fields)
    soql = (f"SELECT {field_list} FROM {object_name} "
            f"WHERE {where_clause} LIMIT {_MAX_ROWS}")
    result = sf.query_all(soql)
    records = result.get('records', [])

    updates = []
    for r in records:
        ch = _transform_record(r, field_rules)
        if ch:
            rec = {'Id': r.get('Id')}
            for c in ch:
                rec[c['field']] = c['after']
            updates.append(rec)

    unchanged = len(records) - len(updates)
    if not updates:
        return {'updated': 0, 'unchanged': unchanged, 'errors': 0, 'total': len(records)}

    if Config.SF_MOCK:
        return {'updated': len(updates), 'unchanged': unchanged, 'errors': 0,
                'total': len(records), 'mock': True}

    if bypass_triggers:
        from sf_provider import set_bypass_triggers
        set_bypass_triggers(sf, True)
    try:
        bulk_obj = getattr(sf.bulk, object_name)
        api_results = bulk_obj.update(updates, batch_size=200)
    finally:
        if bypass_triggers:
            from sf_provider import set_bypass_triggers
            set_bypass_triggers(sf, False)

    updated = sum(1 for x in (api_results or []) if isinstance(x, dict) and x.get('success'))
    errors = len(api_results or []) - updated
    return {'updated': updated, 'unchanged': unchanged, 'errors': errors,
            'total': len(records)}
