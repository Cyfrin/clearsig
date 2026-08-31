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
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# Backstop against pathological include chains. The registry's deepest real
# chain is 2 (kiln -> KilnVaults common -> erc4626 common).
_MAX_INCLUDE_DEPTH = 32


def resolve_includes(descriptor: dict, base_dir: Path) -> dict:
    """Return the fully-resolved copy of ``descriptor`` per ERC-7730.

    Recursively loads and merges `includes` references until no `includes`
    key remains, as required by ERC-8176 before hashing. The input dict is
    not mutated.

    Args:
        descriptor: Parsed ERC-7730 descriptor object.
        base_dir: Directory the descriptor's relative `includes` path is
            resolved against (the descriptor file's parent directory).

    Returns:
        A new dict with every `includes` reference merged in and the
        `includes` keys removed.

    Raises:
        ValueError: If an `includes` value is not a clean string path, the
            include chain contains a cycle, or it exceeds the depth limit.
        OSError: If an included file cannot be read (per ERC-8176, the hash
            cannot be computed when an included file is unavailable).
        json.JSONDecodeError: If an included file is not valid JSON.
    """
    return _resolve(descriptor, base_dir, seen=frozenset(), depth=0)


def _resolve(descriptor: dict, base_dir: Path, seen: frozenset[Path], depth: int) -> dict:
    resolved = copy.deepcopy(descriptor)
    includes = resolved.pop("includes", None)
    if includes is None:
        return resolved

    if depth >= _MAX_INCLUDE_DEPTH:
        raise ValueError(f"includes chain exceeds depth limit ({_MAX_INCLUDE_DEPTH})")
    if not isinstance(includes, str) or not includes or "\x00" in includes:
        raise ValueError(f"'includes' must be a non-empty string path, got {includes!r}")

    include_path = (base_dir / includes).resolve()
    if include_path in seen:
        raise ValueError(f"circular includes chain at {include_path}")

    with open(include_path) as f:
        included = json.load(f)
    if not isinstance(included, dict):
        raise ValueError(f"{include_path}: included descriptor must be a JSON object")

    # Depth-first: fully resolve the included file's own includes chain
    # (relative to *its* directory), then merge the including file over it.
    included = _resolve(included, include_path.parent, seen | {include_path}, depth + 1)
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


def _merge_fields(overlay: list, base: list) -> list:
    """Merge two `fields` arrays by `path` per ERC-7730.

    Entries sharing a `path` are merged (overlay wins); overlay entries with
    a new `path` are appended, preserving the included file's ordering.
    """
    merged = list(base)
    index_by_path = {
        entry.get("path"): i
        for i, entry in enumerate(base)
        if isinstance(entry, dict) and "path" in entry
    }
    for entry in overlay:
        path = entry.get("path") if isinstance(entry, dict) else None
        if path is not None and path in index_by_path:
            i = index_by_path[path]
            merged[i] = _merge(entry, merged[i])
        else:
            merged.append(entry)
    return merged
