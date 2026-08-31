"""ERC-8176 descriptor hash: keccak256 of RFC 8785 JCS-canonicalized JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rfc8785
from eth_hash.auto import keccak

from clearsig._includes import resolve_includes as _resolve_includes


def descriptor_hash(descriptor: Any, *, resolve_includes: bool = True) -> bytes:
    """Compute the ERC-8176 hash of an ERC-7730 descriptor.

    Per ERC-8176, `includes` references are resolved recursively (ERC-7730
    merge rules, `includes` keys removed) so the hash covers the descriptor's
    effective content, then the result is canonicalized per RFC 8785 (JSON
    Canonicalization Scheme) and hashed with keccak256. The hash is therefore
    stable under whitespace, key-order, and encoding differences, and changes
    whenever the content of an included file changes.

    Args:
        descriptor: A parsed JSON object (dict), a JSON string, or a Path to a
            JSON file. Relative `includes` paths are resolved against the
            file's parent directory, so a descriptor that uses `includes`
            must be passed as a Path (or pre-resolved).
        resolve_includes: When False, hash the descriptor exactly as given
            without resolving `includes` (the pre-ERC-8176-final behavior;
            not spec-compliant for descriptors that use `includes`).

    Returns:
        The 32-byte keccak256 digest of the canonicalized JSON.

    Raises:
        TypeError: If descriptor is not a dict, str, or Path.
        ValueError: If the descriptor uses `includes` but was not passed as a
            Path, or the includes chain is malformed (cycle, non-string path,
            depth limit).
        json.JSONDecodeError: If a string or file does not parse as JSON.
        OSError: If a file path (or an included file) cannot be read.
    """
    base_dir: Path | None = None
    if isinstance(descriptor, Path):
        obj = json.loads(descriptor.read_text())
        base_dir = descriptor.resolve().parent
    elif isinstance(descriptor, str):
        obj = json.loads(descriptor)
    elif isinstance(descriptor, dict):
        obj = descriptor
    else:
        raise TypeError(f"unsupported descriptor type: {type(descriptor).__name__}")

    if resolve_includes and isinstance(obj, dict) and "includes" in obj:
        if base_dir is None:
            raise ValueError(
                "descriptor uses 'includes' but has no file location to resolve it "
                "against; pass a Path, pre-resolve with clearsig.resolve_includes(), "
                "or pass resolve_includes=False for the raw hash"
            )
        obj = _resolve_includes(obj, base_dir)

    canonical = rfc8785.dumps(obj)
    return keccak(canonical)


def descriptor_hash_hex(descriptor: Any, *, resolve_includes: bool = True) -> str:
    """Compute the descriptor hash and return it as a 0x-prefixed hex string."""
    return "0x" + descriptor_hash(descriptor, resolve_includes=resolve_includes).hex()
