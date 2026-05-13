"""Tests for the Safe transaction hash module.

Test vector for Safe v1.4.1 + mainnet is taken from the safe-hash-rs README,
which itself is verified against the safe-tx-hashes-util reference script.
"""

from __future__ import annotations

import pytest

from clearsig._safe_hash import (
    APPROVE_HASH_SELECTOR,
    SafeTx,
    _version_lt,
    eip191_hash,
    nested_safe_hashes,
    safe_hashes,
    safe_message_hashes,
    safe_typed_data,
)


class TestSafeHashRsParity:
    """Vector from `safe-hash tx --chain ethereum --nonce 63 --safe-address 0x1c69...`."""

    SAFE_ADDRESS = "0x1c694Fc3006D81ff4a56F97E1b99529066a23725"
    TX = SafeTx(
        to="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        value=0,
        data=(
            "0xa9059cbb"
            "00000000000000000000000092d0ebaf7eb707f0650f9471e61348f4656c29bc"
            "00000000000000000000000000000000000000000000000000000005d21dba00"
        ),
        operation=0,
        nonce=63,
    )

    def test_domain_hash(self) -> None:
        h = safe_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            tx=self.TX,
        )
        assert (
            "0x" + h.domain_hash.hex()
            == "0x1655e94a9bcc5a957daa1acae692b4c22e7aaf146b4deb9194f8221d2f09d8c3"
        )

    def test_message_hash(self) -> None:
        h = safe_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            tx=self.TX,
        )
        assert (
            "0x" + h.message_hash.hex()
            == "0xf22754eba5a2b230714534b4657195268f00dc0031296de4b835d82e7aa1e574"
        )

    def test_safe_tx_hash(self) -> None:
        h = safe_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            tx=self.TX,
        )
        assert (
            "0x" + h.safe_tx_hash.hex()
            == "0xad06b099fca34e51e4886643d95d9a19ace2cd024065efb66662a876e8c40343"
        )


class TestVersionGating:
    def test_v1_3_uses_chain_id_domain(self) -> None:
        td = safe_typed_data(
            chain_id=1,
            safe_address="0x0000000000000000000000000000000000000001",
            safe_version="1.3.0",
            tx=SafeTx(to="0x" + "00" * 20, value=0, data="0x"),
        )
        domain_field_names = [f["name"] for f in td["types"]["EIP712Domain"]]
        assert "chainId" in domain_field_names

    def test_pre_1_3_omits_chain_id_from_domain(self) -> None:
        td = safe_typed_data(
            chain_id=1,
            safe_address="0x0000000000000000000000000000000000000001",
            safe_version="1.2.0",
            tx=SafeTx(to="0x" + "00" * 20, value=0, data="0x"),
        )
        domain_field_names = [f["name"] for f in td["types"]["EIP712Domain"]]
        assert "chainId" not in domain_field_names
        assert domain_field_names == ["verifyingContract"]

    def test_v1_0_uses_base_gas_field(self) -> None:
        td = safe_typed_data(
            chain_id=1,
            safe_address="0x0000000000000000000000000000000000000001",
            safe_version="1.0.0",
            tx=SafeTx(to="0x" + "00" * 20, value=0, data="0x"),
        )
        safe_tx_field_names = [f["name"] for f in td["types"]["SafeTx"]]
        assert "baseGas" in safe_tx_field_names
        assert "dataGas" not in safe_tx_field_names

    def test_pre_1_0_uses_data_gas_field(self) -> None:
        td = safe_typed_data(
            chain_id=1,
            safe_address="0x0000000000000000000000000000000000000001",
            safe_version="0.1.0",
            tx=SafeTx(to="0x" + "00" * 20, value=0, data="0x"),
        )
        safe_tx_field_names = [f["name"] for f in td["types"]["SafeTx"]]
        assert "dataGas" in safe_tx_field_names
        assert "baseGas" not in safe_tx_field_names


class TestVersionLt:
    @pytest.mark.parametrize(
        "version,target,expected",
        [
            ("1.0.0", (1, 3, 0), True),
            ("1.3.0", (1, 3, 0), False),
            ("1.4.1", (1, 3, 0), False),
            ("0.1.0", (1, 0, 0), True),
            ("1.2.9", (1, 3, 0), True),
            ("1", (1, 3, 0), True),  # padding
        ],
    )
    def test_compare(self, version: str, target: tuple[int, ...], expected: bool) -> None:
        assert _version_lt(version, target) is expected

    @pytest.mark.parametrize(
        "version,expected",
        [
            ("1.4.1-rc1", False),  # post-1.3.0 even with suffix
            ("1.2.9+build", True),  # pre-1.3.0 even with suffix
            ("1.4.1.beta", False),  # extra segment ignored
        ],
    )
    def test_handles_version_suffixes(self, version: str, expected: bool) -> None:
        assert _version_lt(version, (1, 3, 0)) is expected

    def test_rejects_unparseable_version(self) -> None:
        with pytest.raises(ValueError, match="unrecognized"):
            _version_lt("not-a-version", (1, 3, 0))


class TestDefaults:
    def test_defaults_match_what_safe_ui_uses(self) -> None:
        """Default tx is a plain CALL with zero gas params and zero address tokens."""
        tx = SafeTx(to="0x" + "00" * 20, value=0, data="0x")
        assert tx.operation == 0
        assert tx.safe_tx_gas == 0
        assert tx.base_gas == 0
        assert tx.gas_price == 0
        assert tx.gas_token == "0x0000000000000000000000000000000000000000"
        assert tx.refund_receiver == "0x0000000000000000000000000000000000000000"
        assert tx.nonce == 0


# safe-hash-rs test_message.txt contents (Sepolia OpenSea sign-in example)
SAFE_HASH_RS_OPENSEA_MESSAGE = (
    "Welcome to OpenSea!\n\n"
    "Click to sign in and accept the OpenSea Terms of Service "
    "(https://opensea.io/tos) and Privacy Policy "
    "(https://opensea.io/privacy).\n\n"
    "This request will not trigger a blockchain transaction or cost any gas fees.\n\n"
    "Wallet address:\n0x657ff0d4ec65d82b2bc1247b0a558bcd2f80a0f1\n\n"
    "Nonce:\nea499f2f-fdbc-4d04-92c4-b60aba887e06"
)


class TestSafeMessageHashes:
    """Vector from `safe-hash msg --chain sepolia --safe-version 1.3.0 ...`."""

    SAFE_ADDRESS = "0x657ff0D4eC65D82b2bC1247b0a558bcd2f80A0f1"

    def test_domain_hash(self) -> None:
        h = safe_message_hashes(
            chain_id=11155111,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.3.0",
            message=SAFE_HASH_RS_OPENSEA_MESSAGE,
        )
        assert (
            "0x" + h.domain_hash.hex()
            == "0x611379c19940caee095cdb12bebe6a9fa9abb74cdb1fbd7377c49a1f198dc24f"
        )

    def test_message_hash(self) -> None:
        h = safe_message_hashes(
            chain_id=11155111,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.3.0",
            message=SAFE_HASH_RS_OPENSEA_MESSAGE,
        )
        assert (
            "0x" + h.message_hash.hex()
            == "0xa5d2f507a16279357446768db4bd47a03bca0b6acac4632a4c2c96af20d6f6e5"
        )

    def test_safe_message_hash(self) -> None:
        h = safe_message_hashes(
            chain_id=11155111,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.3.0",
            message=SAFE_HASH_RS_OPENSEA_MESSAGE,
        )
        assert (
            "0x" + h.safe_message_hash.hex()
            == "0x1866b559f56261ada63528391b93a1fe8e2e33baf7cace94fc6b42202d16ea08"
        )

    def test_crlf_normalizes_to_lf(self) -> None:
        """Carriage returns are stripped so cross-platform inputs hash the same."""
        lf_only = safe_message_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            message="line1\nline2\n",
        )
        crlf = safe_message_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            message="line1\r\nline2\r\n",
        )
        assert lf_only.safe_message_hash == crlf.safe_message_hash

    def test_bytes_input_skips_eip191(self) -> None:
        """When called with bytes, the value is used as raw_message_hash directly."""
        raw = bytes(range(32))
        h = safe_message_hashes(
            chain_id=1,
            safe_address=self.SAFE_ADDRESS,
            safe_version="1.4.1",
            message=raw,
        )
        assert h.raw_message_hash == raw


class TestEip191Hash:
    def test_basic(self) -> None:
        # keccak256("\x19Ethereum Signed Message:\n5hello")
        assert (
            "0x" + eip191_hash("hello").hex()
            == "0x50b2c43fd39106bafbba0da34fc430e1f91e3c96ea2acee2bc34119f92b37750"
        )

    def test_empty(self) -> None:
        # keccak256("\x19Ethereum Signed Message:\n0")
        assert (
            "0x" + eip191_hash("").hex()
            == "0x5f35dce98ba4fba25530a026ed80b2cecdaa31091ba4958b99b52ea1d068adad"
        )


class TestNestedSafeHashes:
    """Vector from `safe-hash tx ... --nested-safe-address ... --nested-safe-nonce 1`."""

    INNER_TX = SafeTx(
        to="0xdd13E55209Fd76AfE204dBda4007C227904f0a81",
        value=0,
        data=(
            "0xa9059cbb"
            "00000000000000000000000036bffa3048d89fad48509c83fdb6a3410232f3d3"
            "00000000000000000000000000000000000000000000000000038d7ea4c68000"
        ),
        operation=0,
        nonce=0,
    )

    def _compute(self):
        return nested_safe_hashes(
            chain_id=11155111,
            inner_safe_address="0xbC7977C6694Ae2Ae8Ad96bb1C100a281D928b7DB",
            inner_safe_version="1.4.1",
            inner_tx=self.INNER_TX,
            outer_safe_address="0x5031f5E2ed384978dca63306dc28A68a6Fc33e81",
            outer_safe_version="1.4.1",
            outer_nonce=1,
        )

    def test_inner_safe_tx_hash(self) -> None:
        assert (
            "0x" + self._compute().inner.safe_tx_hash.hex()
            == "0x2aa2feb008064ccb8d6a31c43a6812d288107501505a04095ecdb2ebbeeaaffc"
        )

    def test_outer_safe_tx_hash(self) -> None:
        assert (
            "0x" + self._compute().outer.safe_tx_hash.hex()
            == "0x2c7a5de4d1bc03ca44ce122ff5feaa4241946737b42ee834a2881fcbe73bfbd6"
        )

    def test_approve_hash_calldata_is_selector_plus_inner_hash(self) -> None:
        n = self._compute()
        assert n.approve_hash_calldata[:4] == APPROVE_HASH_SELECTOR
        assert n.approve_hash_calldata[4:] == n.inner.safe_tx_hash
        assert len(n.approve_hash_calldata) == 36

    def test_approve_hash_selector(self) -> None:
        # keccak256("approveHash(bytes32)")[:4]
        assert bytes.fromhex("d4d9bdcd") == APPROVE_HASH_SELECTOR
