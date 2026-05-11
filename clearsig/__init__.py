"""ERC-7730 calldata translator: convert raw EVM calldata to human-readable output."""

import os
import shutil
import subprocess
from pathlib import Path

from clearsig._abi import decode_calldata, hex_to_bytes
from clearsig._descriptor_hash import descriptor_hash, descriptor_hash_hex
from clearsig._formatter import format_fields
from clearsig._models import TranslatedCalldata, TranslatedField
from clearsig._registry import Registry

__all__ = [
    "Registry",
    "TranslatedCalldata",
    "TranslatedField",
    "descriptor_hash",
    "descriptor_hash_hex",
    "translate",
    "translate_with_registry",
    "update_registry",
]

REGISTRY_REPO = "https://github.com/LedgerHQ/clear-signing-erc7730-registry.git"
DEFAULT_REGISTRY_DIR = Path.home() / ".clearsig" / "registry"

_registry_cache: dict[str, Registry] = {}


def translate(
    calldata: str,
    *,
    to: str,
    chain_id: int,
    registry_path: str | None = None,
    from_address: str | None = None,
) -> TranslatedCalldata:
    """Translate raw calldata to human-readable output using ERC-7730 descriptors.

    Args:
        calldata: Hex-encoded calldata (with or without 0x prefix).
        to: The contract address being called.
        chain_id: The chain ID.
        registry_path: Path to the ERC-7730 registry directory. Falls back to
            ERC7730_REGISTRY_PATH env var, then ~/.clearsig/registry (auto-downloaded).
        from_address: Optional sender address (used for @.from display fields).

    Returns:
        A TranslatedCalldata with the decoded intent, function info, and fields.

    Raises:
        ValueError: If no registry is available or no matching descriptor found.
    """
    registry = _get_registry(registry_path)
    return translate_with_registry(
        registry, calldata, to=to, chain_id=chain_id, from_address=from_address
    )


def translate_with_registry(
    registry: Registry,
    calldata: str,
    *,
    to: str,
    chain_id: int,
    from_address: str | None = None,
) -> TranslatedCalldata:
    """Translate calldata using an already-loaded Registry instance."""
    data = hex_to_bytes(calldata)
    if len(data) < 4:
        raise ValueError(f"Calldata too short ({len(data)} bytes), need at least 4 for selector")

    selector = data[:4]
    func = registry.lookup(selector, chain_id, to)
    if func is None:
        raise ValueError(
            f"No ERC-7730 descriptor found for selector 0x{selector.hex()} "
            f"on {to} (chain {chain_id})"
        )

    decoded = decode_calldata(func.input_types, data[4:])
    decoded_values = dict(zip(func.input_names, decoded, strict=True))

    tx_context = {"to": to}
    if from_address:
        tx_context["from"] = from_address

    fields = format_fields(
        func.display,
        decoded_values,
        func.metadata,
        tx_context,
        registry,
        chain_id,
    )

    return TranslatedCalldata(
        intent=func.display.get("intent", func.name),
        function_name=func.name,
        function_signature=func.signature,
        fields=fields,
        entity=func.entity,
    )


def update_registry(target: str | Path | None = None) -> Path:
    """Download or update the ERC-7730 registry from GitHub.

    Args:
        target: Directory to store the registry. Defaults to ~/.clearsig/registry.

    Returns:
        Path to the registry directory.
    """
    dest = Path(target) if target else DEFAULT_REGISTRY_DIR

    if (dest / ".git").exists():
        subprocess.run(
            ["git", "-C", str(dest), "pull", "--ff-only"],
            check=True,
            capture_output=True,
        )
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(
            ["git", "clone", "--depth", "1", REGISTRY_REPO, str(dest)],
            check=True,
            capture_output=True,
        )

    return dest


def _get_registry(registry_path: str | None) -> Registry:
    path = registry_path or os.environ.get("ERC7730_REGISTRY_PATH")

    if path is None:
        if DEFAULT_REGISTRY_DIR.exists():
            path = str(DEFAULT_REGISTRY_DIR)
        else:
            raise ValueError(
                "No registry found. Run clearsig.update_registry() or "
                "'clearsig update' to download, or set ERC7730_REGISTRY_PATH."
            )

    resolved = os.path.abspath(path)
    if resolved not in _registry_cache:
        _registry_cache[resolved] = Registry.from_path(resolved)
    return _registry_cache[resolved]
