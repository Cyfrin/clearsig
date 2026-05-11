"""Shared input validators used by CLI handlers.

These are early checks that turn malformed user input into a clear error
message instead of a generic eth-abi/eth-hash exception further down the stack.
"""

from __future__ import annotations

import re

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


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
