"""4byte.directory client: reverse-lookup function selectors to text signatures."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from clearsig._validate import is_valid_solidity_signature

DEFAULT_BASE_URL = "https://www.4byte.directory"
DEFAULT_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # 4 MiB — plenty for selector collisions, bounds memory.


def lookup_selector(
    selector: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[str]:
    """Reverse-lookup a 4-byte function selector via 4byte.directory.

    Args:
        selector: Hex-encoded 4-byte selector (with or without 0x prefix).
        base_url: 4byte.directory base URL.
        timeout: Request timeout in seconds.

    Returns:
        Matching text signatures sorted oldest-first (ascending id) — the
        lowest id is the earliest registered signature and the conventional
        choice when picking a canonical match.

    Raises:
        ValueError: If the selector is malformed or the request fails.
    """
    cleaned = selector.strip().lower().removeprefix("0x")
    if len(cleaned) != 8 or any(c not in "0123456789abcdef" for c in cleaned):
        raise ValueError(f"selector must be 4 hex bytes (8 chars), got: {selector!r}")
    hex_signature = "0x" + cleaned

    url = (
        f"{base_url.rstrip('/')}/api/v1/signatures/"
        f"?hex_signature={urllib.parse.quote(hex_signature)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "clearsig"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read(MAX_RESPONSE_BYTES + 1))
    except urllib.error.HTTPError as e:
        raise ValueError(f"4byte.directory request failed ({e.code}): {url}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"4byte.directory request failed: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"4byte.directory returned invalid JSON: {e.msg}") from e

    results = payload.get("results") or []
    results.sort(key=lambda r: r.get("id", 0))
    return [
        r["text_signature"]
        for r in results
        if r.get("text_signature") and is_valid_solidity_signature(r["text_signature"])
    ]
