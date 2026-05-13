"""Shared input/output validators used by CLI handlers.

Input validators turn malformed user input into a clear error message instead
of a generic eth-abi/eth-hash exception further down the stack. Output helpers
make sure strings from untrusted external sources (4byte.directory responses,
registry descriptor labels) can't smuggle terminal escape sequences past the
user — the entire premise of clear-signing is that the displayed bytes match
the signed bytes.
"""

from __future__ import annotations

import re

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Characters legal in a Solidity function signature.
_SIGNATURE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\([A-Za-z0-9_,()\[\]]*\)$")
# C0/C1 controls except tab/newline/CR — backslash-escape these on display so a
# malicious string can't rewrite earlier terminal output.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def validate_address(address: str, *, field: str) -> None:
    """Raise ValueError unless `address` is a 0x-prefixed 40-hex-char string.

    Args:
        address: The address to validate.
        field: Name of the CLI flag (used in the error message, e.g. "--to").
    """
    if not isinstance(address, str) or not _ADDRESS_RE.match(address):
        raise ValueError(f"{field}: not a valid 0x-prefixed 20-byte address: {address!r}")


def validate_hex(value: str, *, field: str, allow_empty: bool = True) -> None:
    """Raise ValueError unless `value` is a valid 0x-prefixed (or bare) hex string.

    Args:
        value: The hex string to validate.
        field: Name of the CLI flag (used in the error message).
        allow_empty: If False, `0x` and `""` are rejected.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected a hex string, got {type(value).__name__}")
    stripped = value[2:] if value.startswith(("0x", "0X")) else value
    if not allow_empty and not stripped:
        raise ValueError(f"{field}: empty hex value")
    if len(stripped) % 2 != 0:
        raise ValueError(f"{field}: hex must have an even number of characters: {value!r}")
    if stripped and not all(c in "0123456789abcdefABCDEF" for c in stripped):
        raise ValueError(f"{field}: contains non-hex characters: {value!r}")


def is_valid_solidity_signature(signature: str) -> bool:
    """Return True if `signature` looks like a real Solidity function signature.

    Used to filter 4byte.directory responses — anyone can submit a signature
    there, including ones with terminal escapes or Unicode lookalikes designed
    to mislead a user picking a signature for `calldata-decode`.
    """
    return isinstance(signature, str) and bool(_SIGNATURE_RE.match(signature))


def sanitize_for_terminal(text: str) -> str:
    """Escape C0/C1 control characters so a malicious string can't rewrite output.

    Tab, newline, and CR are preserved so multi-line output still renders.
    Everything else becomes a `\\xNN` literal.
    """
    return _CONTROL_RE.sub(lambda m: "\\x" + format(ord(m.group()), "02x"), text)
