"""Display formatter: applies ERC-7730 display rules to decoded calldata values."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clearsig._models import TranslatedField

if TYPE_CHECKING:
    from clearsig._registry import Registry


def format_fields(
    display: dict,
    decoded_values: dict[str, Any],
    metadata: dict,
    tx_context: dict[str, str] | None = None,
    registry: Registry | None = None,
    chain_id: int = 1,
) -> list[TranslatedField]:
    """Format decoded calldata values according to ERC-7730 display rules."""
    fields_spec = display.get("fields", [])
    result: list[TranslatedField] = []
    for spec in fields_spec:
        path = spec["path"]
        label = spec["label"]
        fmt = spec.get("format", "raw")
        params = spec.get("params", {})

        raw_value = _resolve_path(path, decoded_values, tx_context)
        formatted = _format_value(
            raw_value, fmt, params, metadata, decoded_values, tx_context,
            registry, chain_id,
        )

        result.append(TranslatedField(label=label, value=formatted, path=path, format=fmt))
    return result


def _resolve_path(
    path: str,
    decoded_values: dict[str, Any],
    tx_context: dict[str, str] | None,
) -> Any:
    """Resolve a field path to its value.

    Handles:
      - Direct param names: "amount"
      - Transaction context: "@.from", "@.to"
      - Nested dot paths: "params.amountIn" (for tuple params)
      - Array iteration: "data.[]" (returns list)
    """
    if path.startswith("@."):
        ctx_key = path[2:]
        return (tx_context or {}).get(ctx_key)

    parts = path.split(".")
    current: Any = decoded_values

    for part in parts:
        if part == "[]":
            break
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None

        if current is None:
            return None

    return current


def _format_value(
    value: Any,
    fmt: str,
    params: dict,
    metadata: dict,
    decoded_values: dict[str, Any],
    tx_context: dict[str, str] | None,
    registry: Registry | None,
    chain_id: int,
) -> str:
    if value is None:
        return "<unknown>"

    if fmt == "raw":
        return _format_raw(value)
    if fmt == "tokenAmount":
        return _format_token_amount(value, params, metadata)
    if fmt == "addressName":
        return _format_address(value)
    if fmt == "enum":
        return _format_enum(value, params, metadata)
    if fmt == "unit":
        return _format_unit(value, params)
    if fmt == "calldata":
        return _format_calldata(
            value, params, decoded_values, tx_context, registry, chain_id,
        )
    return _format_raw(value)


def _format_raw(value: Any) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, bool):
        return str(value)
    return str(value)


def _format_token_amount(value: Any, params: dict, metadata: dict) -> str:
    """Format a token amount, handling thresholds for unlimited approvals."""
    threshold = params.get("threshold")
    if threshold:
        threshold_resolved = _resolve_metadata_ref(threshold, metadata)
        try:
            if isinstance(threshold_resolved, str) and threshold_resolved.startswith("0x"):
                threshold_int = int(threshold_resolved, 16)
            else:
                threshold_int = int(threshold_resolved)
        except (ValueError, TypeError):
            threshold_int = None

        if threshold_int is not None and isinstance(value, int) and value >= threshold_int:
            return params.get("message", "Unlimited")

    return str(value)


def _format_address(value: Any) -> str:
    if isinstance(value, bytes) and len(value) == 20:
        return "0x" + value.hex()
    return str(value)


def _format_enum(value: Any, params: dict, metadata: dict) -> str:
    """Look up an enum value in metadata."""
    enum_dict = params
    if "$ref" in params:
        enum_dict = _resolve_metadata_ref(params["$ref"], metadata)
        if not isinstance(enum_dict, dict):
            enum_dict = {}

    str_value = str(value)
    return enum_dict.get(str_value, str_value)


def _format_unit(value: Any, params: dict) -> str:
    """Format a value with unit (e.g., fee as percentage)."""
    decimals = params.get("decimals", 0)
    base = params.get("base", "")
    if decimals and isinstance(value, int):
        scaled = value / (10**decimals)
        return f"{scaled}{base}"
    return f"{value}{base}"


def _format_calldata(
    value: Any,
    params: dict,
    decoded_values: dict[str, Any],
    tx_context: dict[str, str] | None,
    registry: Registry | None,
    chain_id: int,
) -> str:
    """Recursively decode nested calldata using the registry.

    The params dict may contain:
      - calleePath: path to the target address in decoded_values (e.g., "to")
      - amountPath: path to the value being sent
      - spenderPath: path to the spender address
    """
    if not isinstance(value, bytes) or len(value) < 4:
        return _format_raw(value) if value is not None else "<empty>"

    if registry is None:
        return "0x" + value.hex()

    # Resolve the target address from calleePath
    callee_path = params.get("calleePath")
    callee_address = None
    if callee_path:
        callee_address = _resolve_path(callee_path, decoded_values, tx_context)
        if isinstance(callee_address, bytes):
            callee_address = "0x" + callee_address.hex()

    # Try to decode the nested calldata
    from clearsig._abi import decode_calldata

    selector = value[:4]
    func = registry.lookup(selector, chain_id, callee_address)

    if func is None:
        return "0x" + value.hex()

    try:
        decoded = decode_calldata(func.input_types, value[4:])
        inner_values = dict(zip(func.input_names, decoded, strict=True))
    except Exception:
        return "0x" + value.hex()

    inner_tx_context = {"to": callee_address} if callee_address else None
    inner_fields = format_fields(
        func.display, inner_values, func.metadata, inner_tx_context,
        registry, chain_id,
    )

    intent = func.display.get("intent", func.name)
    entity = func.entity
    parts = [f"{intent} ({entity})" if entity else intent]
    parts.append(f"  -> {func.signature}")
    for field in inner_fields:
        parts.append(f"  {field.label}: {field.value}")
    return "\n".join(parts)


def _resolve_metadata_ref(value: Any, metadata: dict) -> Any:
    """Resolve a $.metadata.X.Y reference to its value in the metadata dict."""
    if not isinstance(value, str) or not value.startswith("$.metadata."):
        return value

    path = value[len("$.metadata."):]
    current: Any = metadata
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return value
    return current if current is not None else value
