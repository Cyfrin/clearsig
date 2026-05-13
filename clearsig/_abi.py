"""ABI utilities: selector computation, calldata encoding/decoding, signature parsing."""

import json

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak


def canonical_type(abi_input: dict) -> str:
    """Convert an ABI input entry to its canonical type string.

    Handles simple types (address, uint256), tuple types with components,
    and array suffixes (tuple[], tuple[3]).
    """
    soltype = abi_input["type"]
    if soltype == "tuple" or soltype.startswith("tuple["):
        components = abi_input.get("components", [])
        inner = ",".join(canonical_type(c) for c in components)
        suffix = soltype[5:]
        return f"({inner}){suffix}"
    return soltype


def compute_selector(name: str, types: list[str]) -> bytes:
    """Compute the 4-byte function selector from a name and canonical types."""
    sig = f"{name}({','.join(types)})"
    return keccak(sig.encode())[:4]


def function_selector(name: str, inputs: list[dict]) -> bytes:
    """Compute the 4-byte function selector from ABI function inputs."""
    types = [canonical_type(inp) for inp in inputs]
    return compute_selector(name, types)


def canonical_signature(name: str, inputs: list[dict]) -> str:
    """Build the canonical function signature string from ABI inputs."""
    types = [canonical_type(inp) for inp in inputs]
    return f"{name}({','.join(types)})"


def decode_calldata(types: list[str], data: bytes) -> tuple:
    """Decode calldata bytes (without the 4-byte selector) using ABI types."""
    return abi_decode(types, data)


def parse_display_signature(sig: str) -> tuple[str, list[str]]:
    """Parse a display format key into (function_name, [canonical_types]).

    Handles both formats:
      - "transfer(address,uint256)"
      - "repay(address asset, uint256 amount, uint256 interestRateMode)"
    """
    paren = sig.index("(")
    name = sig[:paren]
    params_str = sig[paren + 1 : -1]
    if not params_str.strip():
        return name, []

    parts = _split_params(params_str)
    types = []
    for part in parts:
        tokens = part.strip().split()
        types.append(tokens[0])
    return name, types


def _split_params(params_str: str) -> list[str]:
    """Split parameter string on commas, respecting nested parentheses."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in params_str:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def coerce_arg(soltype: str, raw: str):
    """Coerce a CLI string argument into the Python value `eth_abi.encode` expects.

    Supports primitives (address, bool, intN/uintN, bytes/bytesN, string) and
    one level of array nesting via JSON syntax (e.g. `[1,2,3]`, `["0x...","0x..."]`).
    """
    raw = raw.strip()

    if soltype.endswith("]"):
        base = soltype[: soltype.rindex("[")]
        try:
            items = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"expected JSON array for type {soltype}, got: {raw!r} ({e.msg})"
            ) from e
        if not isinstance(items, list):
            raise ValueError(f"expected JSON array for type {soltype}, got: {raw!r}")
        return [coerce_arg(base, _stringify(item)) for item in items]

    if soltype == "bool":
        lowered = raw.lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        raise ValueError(f"expected bool (true/false), got: {raw!r}")

    if soltype.startswith(("uint", "int")):
        return int(raw, 0)

    if soltype == "address":
        return raw

    if soltype == "bytes" or (soltype.startswith("bytes") and soltype[5:].isdigit()):
        return hex_to_bytes(raw)

    if soltype == "string":
        return raw

    raise ValueError(f"unsupported ABI type for CLI encoding: {soltype}")


def _stringify(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, bool):
        return "true" if item else "false"
    return json.dumps(item)


def encode_calldata(signature: str, args: list[str]) -> bytes:
    """Encode a function signature plus string arguments into ABI calldata.

    Returns the 4-byte selector followed by the ABI-encoded parameters.
    """
    name, types = parse_display_signature(signature)
    if len(args) != len(types):
        raise ValueError(f"{name} expects {len(types)} argument(s), got {len(args)}")
    values = [coerce_arg(t, a) for t, a in zip(types, args, strict=True)]
    selector = compute_selector(name, types)
    return selector + abi_encode(types, values)


def encode_calldata_hex(signature: str, args: list[str]) -> str:
    """Hex-encoded (`0x...`) form of :func:`encode_calldata`."""
    return "0x" + encode_calldata(signature, args).hex()


def decode_calldata_with_signature(
    signature: str, calldata: str | bytes
) -> tuple[str, list[str], tuple]:
    """Decode calldata against a function signature.

    Returns ``(name, types, values)``. Raises ``ValueError`` if the calldata's
    4-byte selector doesn't match the signature — a mismatched signature would
    otherwise produce a silent garbage decode.
    """
    name, types = parse_display_signature(signature)
    data = hex_to_bytes(calldata) if isinstance(calldata, str) else calldata
    if len(data) < 4:
        raise ValueError(f"calldata too short ({len(data)} bytes), need at least 4 for selector")

    expected = compute_selector(name, types)
    if data[:4] != expected:
        raise ValueError(
            f"selector mismatch: calldata starts with 0x{data[:4].hex()}, but "
            f"{name}({','.join(types)}) has selector 0x{expected.hex()}"
        )
    values = decode_calldata(types, data[4:])
    return name, types, values


def hex_to_bytes(hex_str: str) -> bytes:
    """Convert a hex string (with or without 0x prefix) to bytes.

    Strips all whitespace so calldata pasted with line breaks works. Odd-length
    hex is rejected — silently padding it would let truncated calldata decode
    to bytes the user didn't intend to sign.
    """
    clean = "".join(hex_str.split()).removeprefix("0x").removeprefix("0X")
    if len(clean) % 2 != 0:
        raise ValueError(
            f"hex must have an even number of characters, got {len(clean)}: {hex_str!r}"
        )
    return bytes.fromhex(clean)
