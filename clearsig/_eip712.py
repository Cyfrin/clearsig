"""EIP-712 typed data hashing.

Implements the typed-data signing scheme used by `eth_signTypedData_v4`:
    digest = keccak256(0x1901 || domainHash || hashStruct(message))

Where:
    hashStruct(s) = keccak256(typeHash(s) || encodeData(s))
    typeHash(T)   = keccak256(typeString(T))
    encodeData(s) = typeHash(s) || enc(field_1) || enc(field_2) || ...

Each `enc(field)` is exactly 32 bytes:
    - atomic (uint, int, address, bool, bytesN): ABI-encoded (left/right-padded)
    - dynamic string/bytes:                       keccak256(value)
    - arrays (fixed or dynamic):                  keccak256(concat(enc(e) for e in v))
    - nested struct:                              hashStruct(struct_type, value)

Spec: https://eips.ethereum.org/EIPS/eip-712
"""

from __future__ import annotations

import re
from typing import Any

from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

# Atomic type names reserved by the EIP-712 spec — a struct definition can't
# shadow them, or the encoded data would silently disagree with verifiers that
# follow the spec.
_ATOMIC_TYPE_RE = re.compile(r"^(?:address|bool|string|bytes\d*|u?int\d*)$")


def hash_typed_data(typed_data: dict) -> bytes:
    """Compute the EIP-712 digest of a typed-data document.

    `typed_data` shape (JSON-compatible):
        {
            "types": {
                "EIP712Domain": [{"name": ..., "type": ...}, ...],
                "<PrimaryType>": [...],
                "<NestedStruct>": [...],
                ...
            },
            "primaryType": "<PrimaryType>",
            "domain": {...},
            "message": {...}
        }
    """
    types: dict = typed_data["types"]
    _reject_atomic_shadowing(types)
    domain_hash = hash_struct("EIP712Domain", types, typed_data["domain"])
    message_hash = hash_struct(typed_data["primaryType"], types, typed_data["message"])
    return keccak(b"\x19\x01" + domain_hash + message_hash)


def _reject_atomic_shadowing(types: dict) -> None:
    for name in types:
        if _ATOMIC_TYPE_RE.match(name):
            raise ValueError(
                f"EIP-712 type {name!r} shadows an atomic type; "
                f"struct names must be distinct from atomic types per the spec"
            )


def hash_domain(typed_data: dict) -> bytes:
    """Compute hashStruct(EIP712Domain) for the document's domain."""
    _reject_atomic_shadowing(typed_data["types"])
    return hash_struct("EIP712Domain", typed_data["types"], typed_data["domain"])


def hash_message(typed_data: dict) -> bytes:
    """Compute hashStruct(primaryType) for the document's message."""
    _reject_atomic_shadowing(typed_data["types"])
    return hash_struct(typed_data["primaryType"], typed_data["types"], typed_data["message"])


def hash_struct(primary_type: str, types: dict, data: dict) -> bytes:
    """Compute hashStruct(T, v) = keccak256(typeHash(T) || encodeData(T, v))."""
    return keccak(_encode_data(primary_type, types, data))


def type_hash(primary_type: str, types: dict) -> bytes:
    """Compute typeHash(T) = keccak256(typeString(T))."""
    return keccak(encode_type(primary_type, types).encode("utf-8"))


def encode_type(primary_type: str, types: dict) -> str:
    """Build the EIP-712 type string for primary_type plus transitively referenced structs.

    Format: `<Primary>(field_type field_name,...)<Dep1>(...)<Dep2>(...)`
    Deps after the primary are listed in alphabetical order.
    """
    deps = _find_dependencies(primary_type, types)
    deps.discard(primary_type)
    ordered = [primary_type, *sorted(deps)]
    return "".join(_one_type_string(t, types) for t in ordered)


def _one_type_string(t: str, types: dict) -> str:
    fields = ",".join(f"{f['type']} {f['name']}" for f in types[t])
    return f"{t}({fields})"


def _find_dependencies(primary_type: str, types: dict, found: set[str] | None = None) -> set[str]:
    """Return the set of struct types reachable from `primary_type` (inclusive)."""
    if found is None:
        found = set()
    if primary_type in found or primary_type not in types:
        return found
    found.add(primary_type)
    for field in types[primary_type]:
        base = _strip_all_arrays(field["type"])
        _find_dependencies(base, types, found)
    return found


def _strip_all_arrays(type_str: str) -> str:
    while type_str.endswith("]"):
        idx = type_str.rindex("[")
        type_str = type_str[:idx]
    return type_str


def _encode_data(primary_type: str, types: dict, data: dict) -> bytes:
    chunks = [type_hash(primary_type, types)]
    for field in types[primary_type]:
        chunks.append(_encode_value(field["type"], data[field["name"]], types))
    return b"".join(chunks)


def _encode_value(field_type: str, value: Any, types: dict) -> bytes:
    """Encode one EIP-712 field to exactly 32 bytes."""
    if field_type in types:
        return hash_struct(field_type, types, value)

    if field_type.endswith("]"):
        idx = field_type.rindex("[")
        inner_type = field_type[:idx]
        if not isinstance(value, list | tuple):
            raise TypeError(f"expected list for {field_type}, got {type(value).__name__}")
        encoded = b"".join(_encode_value(inner_type, v, types) for v in value)
        return keccak(encoded)

    if field_type == "string":
        s = value if isinstance(value, str) else str(value)
        return keccak(s.encode("utf-8"))

    if field_type == "bytes":
        return keccak(_coerce_bytes(value))

    return abi_encode([field_type], [_coerce_atomic(field_type, value)])


def _coerce_atomic(field_type: str, value: Any) -> Any:
    """Coerce a JSON-friendly value to what eth_abi.encode expects for an atomic type."""
    if field_type.startswith(("uint", "int")):
        if isinstance(value, str):
            return int(value, 0) if value.startswith(("0x", "0X")) else int(value)
        return int(value)
    if field_type == "address":
        if isinstance(value, bytes):
            return "0x" + value.hex()
        return value
    if field_type == "bool":
        return bool(value)
    if field_type.startswith("bytes"):
        return _coerce_bytes(value)
    return value


def _coerce_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        hex_str = value[2:] if value.startswith(("0x", "0X")) else value
        return bytes.fromhex(hex_str) if hex_str else b""
    raise TypeError(f"cannot coerce {type(value).__name__} to bytes")
