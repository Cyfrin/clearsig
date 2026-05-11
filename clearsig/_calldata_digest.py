"""ERC-8213 calldata digest: keccak256(uint256(len(calldata)) || calldata).

A length-prefixed fingerprint of raw transaction calldata. Chain ID is
intentionally NOT included — the digest identifies the payload itself, so the
same bytes on different chains hash to the same value.

Spec: https://github.com/ethereum/ERCs/pull/1639
"""

from __future__ import annotations

from eth_hash.auto import keccak

from clearsig._abi import hex_to_bytes


def calldata_digest(calldata: str | bytes) -> bytes:
    """Compute the ERC-8213 calldata digest.

    Args:
        calldata: Hex-encoded calldata (with or without 0x prefix) or raw bytes.
            Empty calldata (0 bytes) is valid — that's a plain ETH transfer —
            and produces a real digest (keccak of 32 zero bytes).

    Returns:
        The 32-byte digest.

    Raises:
        ValueError: If a string input is not valid hex.
    """
    data = calldata if isinstance(calldata, bytes) else hex_to_bytes(calldata)
    length_word = len(data).to_bytes(32, "big")
    return keccak(length_word + data)


def calldata_digest_hex(calldata: str | bytes) -> str:
    """Compute the calldata digest as a 0x-prefixed hex string."""
    return "0x" + calldata_digest(calldata).hex()
