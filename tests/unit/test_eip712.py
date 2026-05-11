"""Tests for the EIP-712 typed-data hasher.

Vectors come from the EIP-712 specification's `Mail` example and chain-tools'
parity fixtures (cyfrin/chain-tools/src/lib/erc8213-parity.test.ts), which
assert byte-for-byte agreement between ethers and viem.
"""

from __future__ import annotations

from typing import Any

import pytest

from clearsig._eip712 import (
    encode_type,
    hash_domain,
    hash_message,
    hash_struct,
    hash_typed_data,
    type_hash,
)

# Canonical EIP-712 spec fixture
MAIL: dict[str, Any] = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Person": [
            {"name": "name", "type": "string"},
            {"name": "wallet", "type": "address"},
        ],
        "Mail": [
            {"name": "from", "type": "Person"},
            {"name": "to", "type": "Person"},
            {"name": "contents", "type": "string"},
        ],
    },
    "primaryType": "Mail",
    "domain": {
        "name": "Ether Mail",
        "version": "1",
        "chainId": 1,
        "verifyingContract": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC",
    },
    "message": {
        "from": {"name": "Cow", "wallet": "0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826"},
        "to": {"name": "Bob", "wallet": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"},
        "contents": "Hello, Bob!",
    },
}

# Permit2 fixture from chain-tools parity test
PERMIT2: dict[str, Any] = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "PermitTransferFrom": [
            {"name": "permitted", "type": "TokenPermissions"},
            {"name": "spender", "type": "address"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "TokenPermissions": [
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
    },
    "primaryType": "PermitTransferFrom",
    "domain": {
        "name": "Permit2",
        "chainId": 1,
        "verifyingContract": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
    },
    "message": {
        "permitted": {
            "token": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "amount": "1000000000",
        },
        "spender": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "nonce": "0",
        "deadline": "1893456000",
    },
}


class TestSpecMail:
    """Spec vectors from EIP-712 itself (https://eips.ethereum.org/EIPS/eip-712)."""

    def test_domain_hash(self) -> None:
        assert (
            "0x" + hash_domain(MAIL).hex()
            == "0xf2cee375fa42b42143804025fc449deafd50cc031ca257e0b194a650a912090f"
        )

    def test_message_hash(self) -> None:
        assert (
            "0x" + hash_message(MAIL).hex()
            == "0xc52c0ee5d84264471806290a3f2c4cecfc5490626bf912d01f240d7a274b371e"
        )

    def test_digest(self) -> None:
        assert (
            "0x" + hash_typed_data(MAIL).hex()
            == "0xbe609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2"
        )

    def test_encode_type_orders_deps_alphabetically(self) -> None:
        # Primary type first, deps after (Person comes after Mail alphabetically anyway)
        assert (
            encode_type("Mail", MAIL["types"])
            == "Mail(Person from,Person to,string contents)Person(string name,address wallet)"
        )

    def test_type_hash_of_person(self) -> None:
        # keccak256("Person(string name,address wallet)") — cross-checked with viem
        assert (
            "0x" + type_hash("Person", MAIL["types"]).hex()
            == "0xb9d8c78acf9b987311de6c7b45bb6a9c8e1bf361fa7fd3467a2163f994c79500"
        )


class TestPermit2:
    """Cross-implementation parity (ethers + viem agree byte-for-byte on these)."""

    def test_digest_is_stable(self) -> None:
        """Locks in the digest so future refactors can't drift."""
        digest = "0x" + hash_typed_data(PERMIT2).hex()
        assert digest == "0x01e5a64a608f03873d795fe77fe6bcd1a15692ee25bc02dd638b8fbc3753625c"

    def test_handles_nested_struct(self) -> None:
        # TokenPermissions inside PermitTransferFrom must round-trip
        h = hash_struct("TokenPermissions", PERMIT2["types"], PERMIT2["message"]["permitted"])
        assert len(h) == 32

    def test_handles_string_uint256_values(self) -> None:
        # JSON quotes uint256 as strings — confirm they coerce correctly
        digest_from_strings = hash_typed_data(PERMIT2)
        coerced_message = {
            **PERMIT2["message"],
            "nonce": 0,
            "deadline": 1893456000,
            "permitted": {**PERMIT2["message"]["permitted"], "amount": 1_000_000_000},
        }
        coerced_doc = {**PERMIT2, "message": coerced_message}
        digest_from_ints = hash_typed_data(coerced_doc)
        assert digest_from_strings == digest_from_ints


class TestTypeStringOrdering:
    def test_dependencies_after_primary_in_alphabetical_order(self) -> None:
        types = {
            "Order": [
                {"name": "asset", "type": "Asset"},
                {"name": "trader", "type": "Trader"},
            ],
            "Asset": [{"name": "kind", "type": "string"}],
            "Trader": [{"name": "wallet", "type": "address"}],
        }
        # Primary 'Order' first, then deps 'Asset', 'Trader' alphabetically
        result = encode_type("Order", types)
        assert result == "Order(Asset asset,Trader trader)Asset(string kind)Trader(address wallet)"

    def test_does_not_double_count_shared_deps(self) -> None:
        types = {
            "Outer": [
                {"name": "a", "type": "Inner"},
                {"name": "b", "type": "Inner"},
            ],
            "Inner": [{"name": "x", "type": "uint256"}],
        }
        # Inner should appear exactly once even though referenced twice
        result = encode_type("Outer", types)
        assert result == "Outer(Inner a,Inner b)Inner(uint256 x)"


class TestArrays:
    def test_dynamic_uint_array(self) -> None:
        types = {
            "EIP712Domain": [{"name": "name", "type": "string"}],
            "Bag": [{"name": "items", "type": "uint256[]"}],
        }
        doc = {
            "types": types,
            "primaryType": "Bag",
            "domain": {"name": "Bag"},
            "message": {"items": [1, 2, 3]},
        }
        # Just confirm it runs and produces a stable 32-byte digest
        digest = hash_typed_data(doc)
        assert len(digest) == 32

    def test_array_length_affects_hash(self) -> None:
        types = {
            "EIP712Domain": [{"name": "name", "type": "string"}],
            "Bag": [{"name": "items", "type": "uint256[]"}],
        }
        common = {"types": types, "primaryType": "Bag", "domain": {"name": "Bag"}}
        a = hash_typed_data({**common, "message": {"items": [1, 2, 3]}})
        b = hash_typed_data({**common, "message": {"items": [1, 2, 3, 4]}})
        assert a != b

    def test_array_of_struct(self) -> None:
        types = {
            "EIP712Domain": [{"name": "name", "type": "string"}],
            "Basket": [{"name": "items", "type": "Item[]"}],
            "Item": [
                {"name": "id", "type": "uint256"},
                {"name": "owner", "type": "address"},
            ],
        }
        doc = {
            "types": types,
            "primaryType": "Basket",
            "domain": {"name": "Basket"},
            "message": {
                "items": [
                    {"id": 1, "owner": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"},
                    {"id": 2, "owner": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"},
                ]
            },
        }
        digest = hash_typed_data(doc)
        assert len(digest) == 32


class TestErrors:
    def test_missing_field_in_message_raises(self) -> None:
        bad = {**MAIL, "message": {"from": MAIL["message"]["from"]}}  # missing 'to', 'contents'
        with pytest.raises(KeyError):
            hash_typed_data(bad)

    def test_non_list_for_array_field_raises(self) -> None:
        types = {
            "EIP712Domain": [{"name": "name", "type": "string"}],
            "Bag": [{"name": "items", "type": "uint256[]"}],
        }
        doc = {
            "types": types,
            "primaryType": "Bag",
            "domain": {"name": "Bag"},
            "message": {"items": "not a list"},
        }
        with pytest.raises(TypeError):
            hash_typed_data(doc)
