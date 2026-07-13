"""Tests for utils.soql — SOQL string-literal escaping + Id validation."""
from utils.soql import escape_soql, is_sf_id


def test_escape_single_quote():
    assert escape_soql("O'Brien") == "O\\'Brien"


def test_escape_backslash_before_quote():
    # Backslash is escaped first so the added quote-escape isn't doubled.
    assert escape_soql("a\\'b") == "a\\\\\\'b"


def test_escape_injection_attempt_is_neutralised():
    # A classic break-out attempt: the closing quote is escaped, so it stays
    # inside the string literal instead of terminating it.
    payload = "x' OR Name != '"
    escaped = escape_soql(payload)
    assert "' OR" not in f"WHERE Id = '{escaped}'".replace("\\'", "")
    assert escaped == "x\\' OR Name != \\'"


def test_escape_plain_value_unchanged():
    assert escape_soql('Account') == 'Account'


def test_escape_coerces_non_str():
    assert escape_soql(123) == '123'


def test_is_sf_id_accepts_15_and_18():
    assert is_sf_id('001000000000001') is True        # 15
    assert is_sf_id('001000000000001AAA') is True      # 18


def test_is_sf_id_rejects_bad():
    assert is_sf_id("001' OR '1'='1") is False
    assert is_sf_id('') is False
    assert is_sf_id(None) is False
    assert is_sf_id('short') is False
