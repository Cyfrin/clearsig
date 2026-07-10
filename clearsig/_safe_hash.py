"""Safe transaction and message hash (offline).

Computes the EIP-712 hashes a Safe wallet displays when an owner is asked to
sign — both for transactions (execTransaction → SafeTx) and for off-chain
messages (signMessage → SafeMessage).

Version compatibility (matches safe-hash-rs):
    - Safe >= 1.3.0: domain is `EIP712Domain(uint256 chainId, address verifyingContract)`
    - Safe <  1.3.0: domain is `EIP712Domain(address verifyingContract)` (chain-agnostic)
    - Safe >= 1.0.0: SafeTx middle field is `baseGas`
    - Safe <  1.0.0: SafeTx middle field is `dataGas`

For nested Safes (an outer Safe owns the inner one), the outer Safe approves
the inner Safe's tx by calling `approveHash(bytes32)` on the inner Safe. This
module computes both the inner Safe Tx Hash and the outer approveHash Safe Tx
Hash.
"""

from __future__ import annotations

from dataclasses import dataclass

from eth_hash.auto import keccak

from clearsig._eip712 import hash_domain, hash_message, hash_typed_data

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
APPROVE_HASH_SELECTOR = b"\xd4\xd9\xbd\xcd"  # keccak256("approveHash(bytes32)")[:4]

# Official MultiSend deployments from safe-global/safe-deployments, keyed by
# lowercased address. These are the only expected DELEGATECALL targets for a
# Safe transaction; anything else deserves the strongest possible warning.
KNOWN_MULTISEND_ADDRESSES: dict[str, str] = {
    "0x8d29be29923b68abfdd21e541b9374737b49cdad": "MultiSend 1.1.1 (canonical)",
    "0xa238cbeb142c10ef7ad8442c6d1f9e89e07e7761": "MultiSend 1.3.0 (canonical)",
    "0x998739bfdaadde7c933b942a68053933098f9eda": "MultiSend 1.3.0 (eip155)",
    "0x0dfcccb95225ffb03c6fbb2559b530c2b7c8a912": "MultiSend 1.3.0 (zksync)",
    "0x38869bf66a61cf6bdb996a6ae40d5853fd43b526": "MultiSend 1.4.1 (canonical)",
    "0x309d0b190fecca8e1d5d8309a16f7e3cb133e885": "MultiSend 1.4.1 (zksync)",
    "0x218543288004cd07832472d464648173c77d7eb7": "MultiSend 1.5.0 (canonical)",
    "0x40a2accbd92bca938b02010e17a5b8929b49130d": "MultiSendCallOnly 1.3.0 (canonical)",
    "0xa1dabef33b3b82c7814b6d82a79e50f4ac44102b": "MultiSendCallOnly 1.3.0 (eip155)",
    "0xf220d3b4dfb23c4ade8c88e526c1353abacbc38f": "MultiSendCallOnly 1.3.0 (zksync)",
    "0x9641d764fc13c8b624c04430c7356c1c7c8102e2": "MultiSendCallOnly 1.4.1 (canonical)",
    "0x0408ef011960d02349d50286d20531229bcef773": "MultiSendCallOnly 1.4.1 (zksync)",
    "0xa83c336b20401af773b6219ba5027174338d1836": "MultiSendCallOnly 1.5.0 (canonical)",
}


def known_multisend(address: str) -> str | None:
    """Name the official Safe MultiSend deployment at `address`, if any."""
    return KNOWN_MULTISEND_ADDRESSES.get(address.lower())


@dataclass(frozen=True)
class SafeTx:
    """A Safe `execTransaction` call payload."""

    to: str
    value: int
    data: bytes | str
    operation: int = 0  # 0 = CALL, 1 = DELEGATECALL
    safe_tx_gas: int = 0
    base_gas: int = 0  # named "dataGas" in Safe < 1.0.0
    gas_price: int = 0
    gas_token: str = ZERO_ADDRESS
    refund_receiver: str = ZERO_ADDRESS
    nonce: int = 0


@dataclass(frozen=True)
class SafeHashes:
    domain_hash: bytes
    message_hash: bytes
    safe_tx_hash: bytes


@dataclass(frozen=True)
class SafeMessageHashes:
    raw_message_hash: bytes  # EIP-191 hash of the plaintext
    domain_hash: bytes
    message_hash: bytes  # struct hash of SafeMessage(bytes message)
    safe_message_hash: bytes  # final keccak256(0x1901 || domain || struct)


@dataclass(frozen=True)
class NestedSafeHashes:
    inner: SafeHashes
    outer: SafeHashes
    approve_hash_calldata: bytes  # what the outer Safe's tx data is


def safe_hashes(
    *,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    tx: SafeTx,
) -> SafeHashes:
    """Compute the three Safe-relevant EIP-712 hashes."""
    typed_data = safe_typed_data(
        chain_id=chain_id, safe_address=safe_address, safe_version=safe_version, tx=tx
    )
    return SafeHashes(
        domain_hash=hash_domain(typed_data),
        message_hash=hash_message(typed_data),
        safe_tx_hash=hash_typed_data(typed_data),
    )


def safe_message_hashes(
    *,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    message: str | bytes,
) -> SafeMessageHashes:
    """Compute the SafeMessage hashes for an off-chain message.

    For string input, line endings are normalized to LF and the plaintext is
    EIP-191 hashed first; the resulting 32-byte hash is then EIP-712 hashed
    inside `SafeMessage(bytes message)`. For bytes input, the value is used as
    the raw_message_hash directly (so callers can pass a pre-hashed value).
    """
    raw_message_hash = eip191_hash(message) if isinstance(message, str) else message

    typed_data = safe_message_typed_data(
        chain_id=chain_id,
        safe_address=safe_address,
        safe_version=safe_version,
        raw_message_hash=raw_message_hash,
    )
    return SafeMessageHashes(
        raw_message_hash=raw_message_hash,
        domain_hash=hash_domain(typed_data),
        message_hash=hash_message(typed_data),
        safe_message_hash=hash_typed_data(typed_data),
    )


def nested_safe_hashes(
    *,
    chain_id: int,
    inner_safe_address: str,
    inner_safe_version: str,
    inner_tx: SafeTx,
    outer_safe_address: str,
    outer_safe_version: str,
    outer_nonce: int,
) -> NestedSafeHashes:
    """Compute hashes for an inner Safe tx + the outer Safe's `approveHash` tx.

    When an outer Safe owns an inner Safe, the outer Safe submits an
    `approveHash(bytes32 hashToApprove)` call to the inner Safe to register its
    approval. This computes hashes for both transactions.
    """
    inner = safe_hashes(
        chain_id=chain_id,
        safe_address=inner_safe_address,
        safe_version=inner_safe_version,
        tx=inner_tx,
    )

    calldata = APPROVE_HASH_SELECTOR + inner.safe_tx_hash
    outer_tx = SafeTx(
        to=inner_safe_address,
        value=0,
        data=calldata,
        operation=0,
        nonce=outer_nonce,
    )
    outer = safe_hashes(
        chain_id=chain_id,
        safe_address=outer_safe_address,
        safe_version=outer_safe_version,
        tx=outer_tx,
    )
    return NestedSafeHashes(inner=inner, outer=outer, approve_hash_calldata=calldata)


def eip191_hash(message: str | bytes) -> bytes:
    """Compute EIP-191 personal_sign hash: keccak256(\\x19Ethereum Signed Message:\\n<len><msg>).

    Strings have line endings normalized to LF before hashing (matches the
    Safe wallet's signMessage UI and safe-hash-rs).
    """
    if isinstance(message, str):
        normalized = message.replace("\r\n", "\n")
        body = normalized.encode("utf-8")
    else:
        body = message
    prefix = f"\x19Ethereum Signed Message:\n{len(body)}".encode()
    return keccak(prefix + body)


def safe_message_typed_data(
    *,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    raw_message_hash: bytes,
) -> dict:
    """Build the EIP-712 typed-data document for a SafeMessage."""
    pre_1_3 = _version_lt(safe_version, (1, 3, 0))
    if pre_1_3:
        domain_fields = [{"name": "verifyingContract", "type": "address"}]
        domain: dict = {"verifyingContract": safe_address}
    else:
        domain_fields = [
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ]
        domain = {"chainId": chain_id, "verifyingContract": safe_address}

    return {
        "types": {
            "EIP712Domain": domain_fields,
            "SafeMessage": [{"name": "message", "type": "bytes"}],
        },
        "primaryType": "SafeMessage",
        "domain": domain,
        "message": {"message": raw_message_hash},
    }


def safe_typed_data(
    *,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    tx: SafeTx,
) -> dict:
    """Build the EIP-712 typed-data document a Safe owner signs."""
    pre_1_3 = _version_lt(safe_version, (1, 3, 0))
    pre_1_0 = _version_lt(safe_version, (1, 0, 0))

    if pre_1_3:
        domain_fields = [{"name": "verifyingContract", "type": "address"}]
        domain: dict = {"verifyingContract": safe_address}
    else:
        domain_fields = [
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ]
        domain = {"chainId": chain_id, "verifyingContract": safe_address}

    middle_field = "dataGas" if pre_1_0 else "baseGas"

    return {
        "types": {
            "EIP712Domain": domain_fields,
            "SafeTx": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "data", "type": "bytes"},
                {"name": "operation", "type": "uint8"},
                {"name": "safeTxGas", "type": "uint256"},
                {"name": middle_field, "type": "uint256"},
                {"name": "gasPrice", "type": "uint256"},
                {"name": "gasToken", "type": "address"},
                {"name": "refundReceiver", "type": "address"},
                {"name": "nonce", "type": "uint256"},
            ],
        },
        "primaryType": "SafeTx",
        "domain": domain,
        "message": {
            "to": tx.to,
            "value": tx.value,
            "data": tx.data,
            "operation": tx.operation,
            "safeTxGas": tx.safe_tx_gas,
            middle_field: tx.base_gas,
            "gasPrice": tx.gas_price,
            "gasToken": tx.gas_token,
            "refundReceiver": tx.refund_receiver,
            "nonce": tx.nonce,
        },
    }


def _version_lt(version: str, target: tuple[int, ...]) -> bool:
    raw = version.split(".")[: len(target)]
    # Accept suffixes like "1.4.1-rc1" or "1.4.1+build" by extracting the
    # leading digits from each segment.
    parsed = []
    for segment in raw:
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            raise ValueError(f"unrecognized Safe version: {version!r}")
        parsed.append(int(digits))
    parts = tuple(parsed) + (0,) * (len(target) - len(parsed))
    return parts < target
