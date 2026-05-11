"""ERC-7730 descriptor generator: build a minimal calldata descriptor from a contract ABI.

Walks each function's inputs into a struct/array/leaf tree, then heuristically picks a
display format per leaf (e.g. uint256 named "amount" → amount; address named "spender"
→ addressName/contract). Output is a starter descriptor — descriptor authors are expected
to refine labels and intents by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from clearsig._abi import canonical_signature

if TYPE_CHECKING:
    from collections.abc import Iterator

SchemaVersion = Literal["v1", "v2"]

_SCHEMA_URLS: dict[SchemaVersion, str] = {
    "v1": "https://github.com/ethereum/clear-signing-erc7730-registry/blob/master/specs/erc7730-v1.schema.json",
    "v2": "https://github.com/ethereum/clear-signing-erc7730-registry/blob/master/specs/erc7730-v2.schema.json",
}

_ARRAY_SUFFIX = re.compile(r"\[(\d*)\]$")


@dataclass(frozen=True)
class StructNode:
    """A tuple / struct: an ordered map of named child trees."""

    components: dict[str, TreeNode]


@dataclass(frozen=True)
class ArrayNode:
    """A dynamic or fixed-size array of a single element tree."""

    element: TreeNode


@dataclass(frozen=True)
class LeafNode:
    """A scalar ABI type: uint, int, ufixed, fixed, address, bool, bytes, string."""

    data_type: str


TreeNode = StructNode | ArrayNode | LeafNode


def generate_descriptor(
    *,
    chain_id: int,
    contract_address: str,
    abi: list[dict],
    owner: str | None = None,
    legal_name: str | None = None,
    url: str | None = None,
    schema_version: SchemaVersion = "v1",
) -> dict:
    """Build an ERC-7730 calldata descriptor dict for `abi` on `chain_id`/`contract_address`.

    Args:
        chain_id: EIP-155 chain ID.
        contract_address: Contract address (any case; emitted as-is).
        abi: ABI list (each entry a dict per Solidity JSON ABI). Non-function entries are ignored.
        owner: Display name for the entity behind the contract.
        legal_name: Full legal name of the owner (paired with `url`).
        url: URL with more info on the owner.
        schema_version: "v1" (default, matches registry) or "v2".

    Returns:
        A descriptor dict ready to be `json.dumps`'d. Includes only `function` ABI entries.
    """
    functions = [e for e in abi if e.get("type") == "function" and e.get("name")]

    formats: dict[str, dict] = {}
    for func in functions:
        signature = canonical_signature(func["name"], func.get("inputs") or [])
        tree = _function_to_tree(func)
        fields = list(_walk(tree, []))
        if fields:
            formats[signature] = {"fields": fields}

    metadata: dict[str, Any] = {}
    if owner:
        metadata["owner"] = owner
    if legal_name and url:
        metadata["info"] = {"legalName": legal_name, "url": url}

    return {
        "$schema": _SCHEMA_URLS[schema_version],
        "context": {
            "contract": {
                "deployments": [{"chainId": chain_id, "address": contract_address}],
                "abi": functions,
            }
        },
        "metadata": metadata,
        "display": {"formats": formats},
    }


def _function_to_tree(function: dict) -> StructNode:
    """Build a tree representing the function's input parameters as a top-level struct."""
    return StructNode(
        components={
            (inp.get("name") or ""): _component_to_tree(inp) for inp in function.get("inputs") or []
        }
    )


def _component_to_tree(component: dict) -> TreeNode:
    """Convert a single ABI input/component dict to a tree node, peeling array suffixes."""
    type_str: str = component["type"]
    base, dims = _strip_array_suffixes(type_str)

    inner: TreeNode
    if base == "tuple":
        inner = StructNode(
            components={
                (c.get("name") or ""): _component_to_tree(c)
                for c in component.get("components") or []
            }
        )
    else:
        inner = LeafNode(data_type=_base_data_type(base))

    for _ in range(dims):
        inner = ArrayNode(element=inner)
    return inner


def _strip_array_suffixes(type_str: str) -> tuple[str, int]:
    """Strip trailing `[]` / `[N]` segments, returning the base type and count."""
    dims = 0
    while (m := _ARRAY_SUFFIX.search(type_str)) is not None:
        type_str = type_str[: m.start()]
        dims += 1
    return type_str, dims


def _base_data_type(base: str) -> str:
    """Normalize a base ABI type to a category used by heuristics."""
    if base.startswith("uint"):
        return "uint"
    if base.startswith("int"):
        return "int"
    if base.startswith("ufixed"):
        return "ufixed"
    if base.startswith("fixed"):
        return "fixed"
    if base.startswith("bytes"):
        return "bytes"
    if base in ("address", "bool", "string"):
        return base
    return base


def _walk(tree: TreeNode, path: list[str]) -> Iterator[dict]:
    """Yield ERC-7730 field entries for every leaf below `tree`, with the given parent `path`."""
    if isinstance(tree, StructNode):
        if not path:
            for name, child in tree.components.items():
                if name:
                    yield from _walk(child, [name])
        else:
            inner_fields: list[dict] = []
            for name, child in tree.components.items():
                if name:
                    inner_fields.extend(_walk(child, [name]))
            yield {"path": ".".join(path), "fields": inner_fields}
        return

    if isinstance(tree, ArrayNode):
        dims = 1
        inner = tree.element
        while isinstance(inner, ArrayNode):
            dims += 1
            inner = inner.element

        array_path = [*path, *(["[]"] * dims)]
        if isinstance(inner, StructNode):
            inner_fields = []
            for name, child in inner.components.items():
                if name:
                    inner_fields.extend(_walk(child, [name]))
            yield {"path": ".".join(array_path), "fields": inner_fields}
        else:
            yield from _walk(inner, array_path)
        return

    name = _last_named_segment(path)
    label = _to_title(name) if name else "Value"
    fmt, params = _pick_format(name, tree.data_type)
    field: dict[str, Any] = {"path": ".".join(path), "label": label, "format": fmt}
    if params:
        field["params"] = params
    yield field


def _last_named_segment(path: list[str]) -> str:
    for segment in reversed(path):
        if segment != "[]":
            return segment
    return ""


def _to_title(name: str) -> str:
    """Convert a parameter name like `_amountIn` or `to_address` to a Title Case label."""
    if not name:
        return ""
    stripped = name.lstrip("_")
    words: list[str] = []
    current = ""
    for ch in stripped:
        if ch == "_":
            if current:
                words.append(current)
                current = ""
        elif ch.isupper() and current and not current[-1].isupper():
            words.append(current)
            current = ch
        else:
            current += ch
    if current:
        words.append(current)
    return " ".join(w[:1].upper() + w[1:] for w in words) if words else stripped


def _pick_format(name: str, data_type: str) -> tuple[str, dict | None]:
    """Heuristically map (parameter name, ABI type) to (ERC-7730 format, params)."""
    n = name.lower()
    match data_type:
        case "uint" | "int":
            if _contains(n, "duration"):
                return "duration", None
            if _contains(n, "height"):
                return "date", {"encoding": "blockheight"}
            if _contains(n, "deadline", "expiration", "until", "time", "timestamp"):
                return "date", {"encoding": "timestamp"}
            if _contains(n, "amount", "value", "price"):
                return "amount", None
            return "raw", None
        case "address":
            if _contains(n, "collection", "nft"):
                return "nftName", {"types": ["collection"]}
            if _contains(n, "spender"):
                return "addressName", {"types": ["contract"]}
            if _contains(n, "asset", "token"):
                return "addressName", {"types": ["token"]}
            if _contains(n, "from", "to", "owner", "recipient", "receiver", "account"):
                return "addressName", {"types": ["eoa", "wallet"]}
            return "addressName", {"types": ["wallet", "eoa", "contract", "token", "collection"]}
        case "bytes":
            if _contains(n, "calldata"):
                return "calldata", None
            return "raw", None
        case _:
            return "raw", None


def _contains(name: str, *needles: str) -> bool:
    return any(needle in name for needle in needles)
