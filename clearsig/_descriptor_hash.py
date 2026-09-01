"""ERC-8176 descriptor hash: keccak256 of RFC 8785 JCS-canonicalized JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import rfc8785
from eth_hash.auto import keccak

from clearsig._includes import default_include_root
from clearsig._includes import resolve_includes as _resolve_includes


def descriptor_hash(
    descriptor: Any, *, resolve_includes: bool = True, include_root: Path | None = None
) -> bytes:
    """Compute the ERC-8176 hash of an ERC-7730 descriptor.

    Per ERC-8176, `includes` references are resolved recursively (ERC-7730
    merge rules, `includes` keys removed) so the hash covers the descriptor's
    effective content, then the result is canonicalized per RFC 8785 (JSON
    Canonicalization Scheme) and hashed with keccak256. The hash is therefore
    stable under whitespace, key-order, and encoding differences, and changes
    whenever the content of an included file changes.

    Containment: in the default mode, a Path descriptor is confined to the
    include root *before it is read* — the root is inferred from the path's
    lexical location (or taken from ``include_root``), the path is resolved
    (following symlinks), and a descriptor that resolves outside the root is
    rejected whether or not it uses `includes`. Legacy raw mode
    (``resolve_includes=False``) deliberately reads whatever the given path
    yields, with no containment.

    Args:
        descriptor: A parsed JSON object (dict), a JSON string, or a Path to a
            JSON file. Relative `includes` paths are resolved against the
            file's lexical parent directory, so a descriptor that uses
            `includes` must be passed as a Path (or pre-resolved). ERC-8176
            defines the hash over a descriptor *object*; non-object JSON is
            rejected.
        resolve_includes: When False, hash the descriptor exactly as given
            without resolving `includes` and without containment (legacy
            behavior predating the 2026-05-21 ERC-8176 draft change; not
            spec-conformant for descriptors that use `includes`).
        include_root: Trusted directory the descriptor file (after following
            symlinks) and every resolved include must stay inside. Defaults
            to the registry checkout root inferred from the descriptor's
            lexical location (see
            :func:`clearsig._includes.default_include_root`).

    Returns:
        The 32-byte keccak256 digest of the canonicalized JSON.

    Raises:
        TypeError: If descriptor is not a dict, str, or Path.
        ValueError: If the parsed descriptor is not a JSON object; if it uses
            `includes` but was not passed as a Path; if the descriptor file
            resolves outside the include root (e.g. a symlinked descriptor —
            checked before the file is read); or if the includes chain is
            invalid (escapes the root, URI scheme, cycle, null/non-string
            value, depth limit, duplicate `fields` paths in a merge).
        json.JSONDecodeError: If a string or file does not parse as JSON.
        OSError: If a file path (or an included file) cannot be read.
    """
    base_dir: Path | None = None
    resolved_root: Path | None = None
    if isinstance(descriptor, Path):
        if resolve_includes:
            # Containment BEFORE reading, for every Path descriptor: infer
            # the root from the lexical location (symlinks not followed),
            # then require the resolved file to sit inside it — whether or
            # not the content turns out to use `includes`.
            base_dir = Path(os.path.normpath(descriptor.absolute())).parent
            root = include_root if include_root is not None else default_include_root(base_dir)
            resolved_root = root.resolve()
            resolved_file = descriptor.resolve()
            try:
                resolved_file.relative_to(resolved_root)
            except ValueError as e:
                raise ValueError(
                    f"descriptor resolves outside the include root {resolved_root} "
                    "(symlinked descriptor?); pass include_root explicitly to allow this"
                ) from e
            obj = json.loads(resolved_file.read_text())
        else:
            # Legacy raw mode: hash whatever the given path yields, as-is.
            obj = json.loads(descriptor.read_text())
    elif isinstance(descriptor, str):
        obj = json.loads(descriptor)
    elif isinstance(descriptor, dict):
        obj = descriptor
    else:
        raise TypeError(f"unsupported descriptor type: {type(descriptor).__name__}")

    if not isinstance(obj, dict):
        raise ValueError(f"ERC-7730 descriptor must be a JSON object, got {type(obj).__name__}")

    if resolve_includes and "includes" in obj:
        if base_dir is None or resolved_root is None:
            raise ValueError(
                "descriptor uses 'includes' but has no file location to resolve it "
                "against; pass a Path, pre-resolve with clearsig.resolve_includes(), "
                "or pass resolve_includes=False for the legacy raw hash"
            )
        obj = _resolve_includes(obj, base_dir, root=resolved_root)

    canonical = rfc8785.dumps(obj)
    return keccak(canonical)


def descriptor_hash_hex(
    descriptor: Any, *, resolve_includes: bool = True, include_root: Path | None = None
) -> str:
    """Compute the descriptor hash and return it as a 0x-prefixed hex string."""
    return (
        "0x"
        + descriptor_hash(
            descriptor, resolve_includes=resolve_includes, include_root=include_root
        ).hex()
    )
