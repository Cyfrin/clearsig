"""ERC-8176 descriptor hash: keccak256 of RFC 8785 JCS-canonicalized JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rfc8785
from eth_hash.auto import keccak


def descriptor_hash(descriptor: Any) -> bytes:
    """Compute the keccak256 of the JCS-canonicalized descriptor JSON.

    The descriptor is canonicalized per RFC 8785 (JSON Canonicalization Scheme)
    before hashing, so the result is stable under whitespace, key-order, and
    encoding differences in the input file.

    Args:
        descriptor: A parsed JSON object (dict), a JSON string, or a Path to a
            JSON file.

    Returns:
        The 32-byte keccak256 digest of the canonicalized JSON.

    Raises:
        TypeError: If descriptor is not a dict, str, or Path.
        json.JSONDecodeError: If a string or file does not parse as JSON.
        OSError: If a file path cannot be read.
    """
    if isinstance(descriptor, Path):
        obj = json.loads(descriptor.read_text())
    elif isinstance(descriptor, str):
        obj = json.loads(descriptor)
    elif isinstance(descriptor, dict):
        obj = descriptor
    else:
        raise TypeError(f"unsupported descriptor type: {type(descriptor).__name__}")

    canonical = rfc8785.dumps(obj)
    return keccak(canonical)


def descriptor_hash_hex(descriptor: Any) -> str:
    """Compute the descriptor hash and return it as a 0x-prefixed hex string."""
    return "0x" + descriptor_hash(descriptor).hex()
