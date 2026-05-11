"""Sourcify v2 client: fetch verified contract ABIs, traversing proxies."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

from clearsig._abi import function_selector

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_BASE_URL = "https://sourcify.dev/server"
DEFAULT_TIMEOUT_SECONDS = 15
MAX_PROXY_DEPTH = 3


def fetch_abi(
    chain_id: int,
    address: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    warn: Callable[[str], None] | None = None,
) -> tuple[list[dict], list[str], str | None]:
    """Fetch a verified contract's ABI from Sourcify v2, auto-traversing proxies.

    For proxy contracts (EIP-1967, ZeppelinOS, EIP-1822, Diamond, etc.), Sourcify
    reports `proxyResolution.implementations`. We follow those to their ABIs and
    union function entries by selector. Cycle-protected with a max depth.

    Args:
        chain_id: EIP-155 chain ID.
        address: Contract address (with or without 0x prefix).
        base_url: Sourcify server base URL.
        warn: Optional callback for informational warnings (proxy traversal,
            non-exact matches).

    Returns:
        (abi, addresses_visited, match_level) where `abi` is the resolved ABI
        list (proxy implementation ABI when applicable), `addresses_visited` is
        the chain of addresses traversed in order, and `match_level` is the
        Sourcify match level of the *first* address ("exact_match", "match", or
        None if unverified).

    Raises:
        ValueError: If the contract is not verified, the network call fails, or
            proxy traversal exceeds MAX_PROXY_DEPTH.
    """
    address = _normalize_address(address)
    warn = warn or (lambda _msg: None)

    visited: list[str] = []
    seen: set[str] = set()
    abi_by_selector: dict[bytes, dict] = {}
    non_function_entries: list[dict] = []
    first_match: str | None = None
    pending: list[str] = [address]

    for depth in range(MAX_PROXY_DEPTH + 1):
        if not pending:
            break

        next_addresses: list[str] = []
        for addr in pending:
            if addr in seen:
                continue
            seen.add(addr)
            visited.append(addr)

            data = _fetch_one(chain_id, addr, base_url)
            match_level = data.get("match")

            if depth == 0:
                first_match = match_level
                if match_level not in ("exact_match", "match"):
                    raise ValueError(
                        f"Contract {addr} on chain {chain_id} is not verified on "
                        f"Sourcify. Provide an ABI explicitly with --abi <path>."
                    )

            _merge_abi(data.get("abi") or [], abi_by_selector, non_function_entries)

            resolution = data.get("proxyResolution") or {}
            if resolution.get("isProxy"):
                impls = resolution.get("implementations") or []
                impl_addresses = [
                    _normalize_address(i["address"]) for i in impls if i.get("address")
                ]
                if impl_addresses:
                    proxy_type = resolution.get("proxyType") or "proxy"
                    impl_list = ", ".join(impl_addresses)
                    warn(f"{addr} is a {proxy_type}; following to {impl_list}")
                    next_addresses.extend(impl_addresses)

        pending = next_addresses
    else:
        raise ValueError(f"Proxy chain starting at {address} exceeded max depth {MAX_PROXY_DEPTH}.")

    abi = list(abi_by_selector.values()) + non_function_entries
    return abi, visited, first_match


def _fetch_one(chain_id: int, address: str, base_url: str) -> dict:
    """Fetch a single contract record from Sourcify v2."""
    url = (
        f"{base_url.rstrip('/')}/v2/contract/{chain_id}/{address}"
        f"?fields={urllib.parse.quote('abi,proxyResolution')}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "clearsig/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(
                f"Contract {address} on chain {chain_id} not found on Sourcify. "
                f"Verify the address, or provide an ABI with --abi <path>."
            ) from e
        raise ValueError(f"Sourcify request failed ({e.code}): {url}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Sourcify request failed: {e.reason}") from e

    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"Sourcify returned invalid JSON: {e.msg}") from e


def _merge_abi(
    entries: list[dict],
    funcs_by_selector: dict[bytes, dict],
    other_entries: list[dict],
) -> None:
    """Merge ABI entries: dedupe functions by selector, keep others as-is."""
    for entry in entries:
        if entry.get("type") == "function":
            try:
                selector = function_selector(entry["name"], entry.get("inputs", []) or [])
            except (KeyError, ValueError):
                continue
            funcs_by_selector.setdefault(selector, entry)
        else:
            other_entries.append(entry)


def _normalize_address(address: str) -> str:
    """Lowercase, 0x-prefixed address."""
    addr = address.lower().strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    if len(addr) != 42 or not all(c in "0123456789abcdef" for c in addr[2:]):
        raise ValueError(f"Invalid address: {address}")
    return addr
