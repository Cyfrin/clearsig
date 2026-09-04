"""ERC-7730 `includes` resolution.

An ERC-7730 descriptor may reference a shared descriptor file via the
top-level `includes` key. ERC-8176 requires the descriptor hash to cover the
fully-resolved descriptor: `includes` references are resolved recursively per
the ERC-7730 merge rules until no `includes` key remains.

Merge rules (ERC-7730 "Descriptor inclusion" section):

- The two files are deep-merged; on conflicting unique keys the *including*
  file wins.
- Field format specifications (`fields` arrays) are merged element-wise by
  their `path` value: entries sharing a `path` are merged (including file
  wins), entries whose `path` is not present in the included file are
  appended.
- The `includes` key itself is dropped from the resolved result.

Scope: ERC-7730 allows `includes` to be a URL; this resolver supports local
registry paths only and rejects URI schemes explicitly. Every resolved
include must stay inside a trusted root directory (see
:func:`default_include_root`), so a descriptor cannot read arbitrary host
files via `../` traversal, absolute paths, or symlinks.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

# Backstop against pathological include chains. The registry's deepest real
# chain is 2 (kiln -> KilnVaults common -> erc4626 common).
_MAX_INCLUDE_DEPTH = 32

_MISSING = object()

# Any URI scheme (RFC 3986 `scheme:`), not just `scheme://` — catches
# `https:example.com/x`, `file:/tmp/x`, `urn:example:x`, etc.
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def default_include_root(base_dir: Path) -> Path:
    """Infer the trusted include root for a descriptor directory.

    Works on the *lexical* path — symlinks are deliberately not followed, so
    a symlinked descriptor cannot relocate root inference to wherever its
    target lives. Walks up from ``base_dir`` looking for the ERC-7730
    registry layout: an ancestor directory named ``registry`` or ``ercs``
    whose parent contains **both** sibling ``registry/`` and ``ercs/`` as
    real, non-symlink directories (a symlinked marker must not widen the
    root). That parent (the registry checkout root) is returned, so
    cross-tree references like ``../../ercs/calldata-erc4626-vaults.json``
    resolve while staying inside the checkout. When no such layout exists the
    root falls back to ``base_dir`` itself (a standalone descriptor may then
    only include files from its own directory tree).
    """
    lexical = Path(os.path.normpath(base_dir.absolute()))
    for ancestor in (lexical, *lexical.parents):
        if ancestor.name in ("registry", "ercs"):
            candidate = ancestor.parent
            if _is_real_dir(candidate / "registry") and _is_real_dir(candidate / "ercs"):
                return candidate
    return lexical


def _is_real_dir(path: Path) -> bool:
    """True for an actual directory that is not itself a symlink."""
    return path.is_dir() and not path.is_symlink()


def resolve_includes(descriptor: dict, base_dir: Path, *, root: Path | None = None) -> dict:
    """Return the fully-resolved copy of ``descriptor`` per ERC-7730.

    Recursively loads and merges `includes` references until no `includes`
    key remains, as required by ERC-8176 before hashing. The input dict is
    not mutated.

    Args:
        descriptor: Parsed ERC-7730 descriptor object.
        base_dir: Directory the descriptor's relative `includes` path is
            resolved against (the descriptor file's parent directory).
        root: Trusted directory every resolved include must stay inside.
            Defaults to :func:`default_include_root` of ``base_dir``.

    Returns:
        A new dict with every `includes` reference merged in and the
        `includes` keys removed.

    Raises:
        ValueError: If the descriptor is not a JSON object; if an `includes`
            value is null, empty, not a string, or carries a URI scheme
            (clearsig resolves local registry paths only); if a resolved
            include escapes ``root``; if the chain contains a cycle or
            exceeds the depth limit; or if duplicate `path` values appear in
            either `fields` array participating in a merge (merge order for
            duplicates is undefined by ERC-7730; duplicates in arrays that
            never merge are left as written).
        OSError: If an included file cannot be read (per ERC-8176, the hash
            cannot be computed when an included file is unavailable).
        json.JSONDecodeError: If an included file is not valid JSON.
    """
    if not isinstance(descriptor, dict):
        raise ValueError(
            f"ERC-7730 descriptor must be a JSON object, got {type(descriptor).__name__}"
        )
    resolved_root = (root if root is not None else default_include_root(base_dir)).resolve()
    return _resolve(descriptor, base_dir, resolved_root, seen=frozenset(), depth=0)


def _resolve(
    descriptor: dict, base_dir: Path, root: Path, seen: frozenset[Path], depth: int
) -> dict:
    resolved = copy.deepcopy(descriptor)
    includes = resolved.pop("includes", _MISSING)
    if includes is _MISSING:
        return resolved

    if depth >= _MAX_INCLUDE_DEPTH:
        raise ValueError(f"includes chain exceeds depth limit ({_MAX_INCLUDE_DEPTH})")
    if not isinstance(includes, str) or not includes or "\x00" in includes:
        raise ValueError(f"'includes' must be a non-empty string path, got {includes!r}")
    if _URI_SCHEME.match(includes):
        raise ValueError(
            f"URI includes are not supported: {includes!r}; "
            "clearsig resolves local registry paths only"
        )

    include_path = (base_dir / includes).resolve()
    try:
        include_path.relative_to(root)
    except ValueError as e:
        raise ValueError(
            f"'includes' escapes the include root {root}: {includes!r} "
            "(pass an explicit wider root to allow this)"
        ) from e
    if include_path in seen:
        raise ValueError(f"circular includes chain at {include_path}")

    with open(include_path) as f:
        included = json.load(f)
    if not isinstance(included, dict):
        raise ValueError(f"{include_path}: included descriptor must be a JSON object")

    # Depth-first: fully resolve the included file's own includes chain
    # (relative to *its* directory), then merge the including file over it.
    included = _resolve(included, include_path.parent, root, seen | {include_path}, depth + 1)
    return _merge(resolved, included)


def _merge(overlay: Any, base: Any) -> Any:
    """Deep-merge ``overlay`` (the including file, wins) over ``base``."""
    if isinstance(overlay, dict) and isinstance(base, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if key in merged:
                if key == "fields" and isinstance(value, list) and isinstance(merged[key], list):
                    merged[key] = _merge_fields(value, merged[key])
                else:
                    merged[key] = _merge(value, merged[key])
            else:
                merged[key] = value
        return merged
    # Conflicting non-dict values (including arrays other than `fields`):
    # the including file wins wholesale.
    return overlay


def _index_fields_by_path(entries: list, which: str) -> dict:
    """Index a `fields` array by `path`, rejecting duplicate paths.

    ERC-7730 defines the merge per-`path` but does not define behavior for
    duplicate `path` values within one array; different implementations could
    resolve them differently and compute different hashes, so we refuse.
    """
    index: dict[Any, int] = {}
    for i, entry in enumerate(entries):
        path = entry.get("path") if isinstance(entry, dict) else None
        if path is None:
            continue
        if path in index:
            raise ValueError(
                f"duplicate fields path {path!r} in the {which} descriptor; "
                "merge behavior for duplicate paths is undefined by ERC-7730"
            )
        index[path] = i
    return index


def _merge_fields(overlay: list, base: list) -> list:
    """Merge two `fields` arrays by `path` per ERC-7730.

    Entries sharing a `path` are merged (overlay wins); overlay entries with
    a new `path` are appended, preserving the included file's ordering.
    """
    merged = list(base)
    base_index = _index_fields_by_path(base, "included")
    _index_fields_by_path(overlay, "including")  # duplicate check only
    for entry in overlay:
        path = entry.get("path") if isinstance(entry, dict) else None
        if path is not None and path in base_index:
            i = base_index[path]
            merged[i] = _merge(entry, merged[i])
        else:
            merged.append(entry)
    return merged
