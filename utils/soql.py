"""Shared SOQL-safety helpers.

Endpoints that build a SOQL query from a *discrete* identifier or search term
(a user id, a permission-set id, an object name, a search box) must escape that
value so a quote can't break out of the string literal. This is distinct from
the SOQL Workbench / Data Ops `where_clause`, which run operator-authored SOQL
by design.
"""
import re

_SF_ID = re.compile(r'^[a-zA-Z0-9]{15,18}$')


def escape_soql(value) -> str:
    """Escape the characters that can break out of a SOQL string literal.

    Backslash first (so the quote-escapes we add aren't themselves doubled),
    then the single quote. Mirrors the SOQL string-escaping rules; safe to apply
    to already-trusted values (real ids contain none of these characters).
    """
    return str(value).replace('\\', '\\\\').replace("'", "\\'")


def is_sf_id(value) -> bool:
    """True if value looks like a 15- or 18-char Salesforce Id (alphanumeric)."""
    return bool(_SF_ID.match(str(value or '')))
