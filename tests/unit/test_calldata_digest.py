"""Tests for ERC-8213 calldata digest.

Vectors are taken from chain-tools' reference implementation
(cyfrin/chain-tools/src/lib/calldata-digest.test.ts).
"""

from __future__ import annotations

import pytest

from clearsig._calldata_digest import calldata_digest, calldata_digest_hex

ERC20_TRANSFER_CALLDATA = (
    "0xa9059cbb"
    "0000000000000000000000004675c7e5baafbffbca748158becba61ef3b0a263"
    "0000000000000000000000000000000000000000000000000de0b6b3a7640000"
)
ERC20_TRANSFER_DIGEST = "0x812cee5d9cc7461c04bbcd7b70af9c28b243ac5d74d3453b008b93b7dac69985"


class TestSpecVectors:
    def test_erc20_transfer_matches_chain_tools(self) -> None:
        assert calldata_digest_hex(ERC20_TRANSFER_CALLDATA) == ERC20_TRANSFER_DIGEST

    def test_empty_calldata_is_keccak_of_32_zero_bytes(self) -> None:
        """Plain ETH transfer has 0 bytes of calldata — the length prefix is 32 zero bytes."""
        assert (
            calldata_digest_hex("0x")
            == "0x290decd9548b62a8d60345a988386fc84ba6bc95484008f6362f93160ef3e563"
        )


class TestInputFormats:
    def test_without_0x_prefix(self) -> None:
        with_prefix = calldata_digest_hex(ERC20_TRANSFER_CALLDATA)
        without_prefix = calldata_digest_hex(ERC20_TRANSFER_CALLDATA[2:])
        assert with_prefix == without_prefix

    def test_accepts_raw_bytes(self) -> None:
        as_bytes = calldata_digest_hex(bytes.fromhex(ERC20_TRANSFER_CALLDATA[2:]))
        as_hex = calldata_digest_hex(ERC20_TRANSFER_CALLDATA)
        assert as_bytes == as_hex

    def test_returns_32_bytes(self) -> None:
        digest = calldata_digest("0xdeadbeef")
        assert len(digest) == 32


class TestEdgeCases:
    def test_different_inputs_produce_different_digests(self) -> None:
        a = calldata_digest_hex("0xdeadbeef")
        b = calldata_digest_hex("0xcafebabe")
        assert a != b

    def test_length_prefix_prevents_shared_prefix_collisions(self) -> None:
        """`0xdeadbeef` and `0xdeadbeef00` differ in length, so their digests must differ."""
        short = calldata_digest_hex("0xdeadbeef")
        long = calldata_digest_hex("0xdeadbeef00")
        assert short != long

    @pytest.mark.parametrize("invalid", ["0xzz", "not-hex"])
    def test_invalid_hex_raises(self, invalid: str) -> None:
        with pytest.raises(ValueError):
            calldata_digest_hex(invalid)
