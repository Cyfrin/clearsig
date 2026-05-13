"""Tests for clearsig._validate helpers."""

from __future__ import annotations

import pytest

from clearsig._validate import (
    is_valid_solidity_signature,
    sanitize_for_terminal,
    validate_address,
    validate_hex,
)


class TestValidateAddress:
    def test_accepts_lower_and_mixed_case(self):
        validate_address("0x" + "ab" * 20, field="--to")
        validate_address("0xA0b86991C6218B36C1D19D4a2E9eb0CE3606EB48", field="--to")

    def test_rejects_short(self):
        with pytest.raises(ValueError, match="--to"):
            validate_address("0xabcd", field="--to")

    def test_rejects_missing_prefix(self):
        with pytest.raises(ValueError):
            validate_address("ab" * 20, field="--to")


class TestValidateHex:
    def test_rejects_odd_length(self):
        with pytest.raises(ValueError, match="even number"):
            validate_hex("0xabc", field="--data")

    def test_accepts_empty(self):
        validate_hex("0x", field="--data")

    def test_rejects_empty_when_disallowed(self):
        with pytest.raises(ValueError, match="empty"):
            validate_hex("0x", field="--data", allow_empty=False)


class TestIsValidSoliditySignature:
    def test_accepts_canonical(self):
        assert is_valid_solidity_signature("approve(address,uint256)")
        assert is_valid_solidity_signature("multicall(bytes[])")
        assert is_valid_solidity_signature("noop()")

    def test_accepts_nested(self):
        assert is_valid_solidity_signature("submit((address,uint256)[],bytes)")

    def test_rejects_ansi_escapes(self):
        assert not is_valid_solidity_signature("approve(address,uint256)\x1b[2A")

    def test_rejects_unicode_lookalike(self):
        # Cyrillic 'а' (U+0430) in place of Latin 'a'
        assert not is_valid_solidity_signature("аpprove(address,uint256)")

    def test_rejects_no_parens(self):
        assert not is_valid_solidity_signature("approve")

    def test_rejects_garbage(self):
        assert not is_valid_solidity_signature("'; rm -rf /;")


class TestSanitizeForTerminal:
    def test_preserves_safe_text(self):
        assert sanitize_for_terminal("Transfer 1 USDC to 0xabc") == "Transfer 1 USDC to 0xabc"

    def test_preserves_tab_newline_cr(self):
        assert sanitize_for_terminal("a\tb\nc\rd") == "a\tb\nc\rd"

    def test_escapes_ansi(self):
        # \x1b is the ESC that starts ANSI sequences; must not pass through.
        out = sanitize_for_terminal("safe\x1b[31mDANGER\x1b[0m")
        assert "\x1b" not in out
        assert "\\x1b" in out

    def test_escapes_c1_controls(self):
        # \x9b is the C1 CSI — equivalent to ESC[ in 8-bit terminals.
        out = sanitize_for_terminal("\x9b2A")
        assert "\x9b" not in out
        assert "\\x9b" in out
