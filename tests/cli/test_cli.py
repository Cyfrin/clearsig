"""CLI tests that invoke the clearsig command as a subprocess."""

import json
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from eth_abi import encode

from clearsig._abi import compute_selector

REGISTRY_PATH = Path(__file__).parent.parent.parent / "clear-signing-erc7730-registry"

USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
AAVE_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
SAFE_1_4_1 = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
MULTISEND = "0x38869bf66a61cF6bDB996A6aE40D5853Fd43B526"
USER = "0x9467919138E36f0252886519f34a0f8016dDb3a3"
ZERO = "0x0000000000000000000000000000000000000000"
UNISWAP_ROUTER = "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"


@pytest.fixture()
def registry_available() -> Path:
    if not REGISTRY_PATH.exists():
        pytest.skip("Local registry not available")
    return REGISTRY_PATH


def _run_cli(*args: str, expect_error: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, "-m", "clearsig", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not expect_error:
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return result


# ── Calldata builders ────────────────────────────────────────────────────────


def _erc20_approve_calldata(spender: str, amount: int) -> bytes:
    sel = compute_selector("approve", ["address", "uint256"])
    return sel + encode(["address", "uint256"], [spender, amount])


def _aave_supply_calldata(asset: str, amount: int, on_behalf_of: str) -> bytes:
    sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
    return sel + encode(
        ["address", "uint256", "address", "uint16"],
        [asset, amount, on_behalf_of, 0],
    )


def _safe_exec_calldata(
    to: str,
    inner: bytes,
    operation: int = 0,
    from_addr: str | None = None,
) -> str:
    sel = compute_selector(
        "execTransaction",
        [
            "address",
            "uint256",
            "bytes",
            "uint8",
            "uint256",
            "uint256",
            "uint256",
            "address",
            "address",
            "bytes",
        ],
    )
    params = encode(
        [
            "address",
            "uint256",
            "bytes",
            "uint8",
            "uint256",
            "uint256",
            "uint256",
            "address",
            "address",
            "bytes",
        ],
        [to, 0, inner, operation, 0, 0, 0, ZERO, ZERO, b""],
    )
    return "0x" + sel.hex() + params.hex()


def _pack_multisend_tx(op: int, to: str, value: int, data: bytes) -> bytes:
    to_bytes = bytes.fromhex(to[2:])
    return (
        struct.pack("B", op)
        + to_bytes
        + value.to_bytes(32, "big")
        + len(data).to_bytes(32, "big")
        + data
    )


# ── README example tests ────────────────────────────────────────────────────


class TestSafeApproveExample:
    """Safe execTransaction wrapping an ERC-20 approve."""

    def test_decodes_outer_safe_layer(self, registry_available: Path):
        inner = _erc20_approve_calldata(AAVE_POOL, 1_000_000)
        calldata = _safe_exec_calldata(USDC, inner)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
        )
        assert "Intent: sign multisig operation" in result.stdout
        assert "Operation type: Call" in result.stdout
        assert f"From Safe: {SAFE_1_4_1}" in result.stdout
        assert f"Execution signer: {USER}" in result.stdout

    def test_recursively_decodes_inner_approve(self, registry_available: Path):
        inner = _erc20_approve_calldata(AAVE_POOL, 1_000_000)
        calldata = _safe_exec_calldata(USDC, inner)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
        )
        assert "Approve" in result.stdout
        assert "approve(address,uint256)" in result.stdout
        assert "Spender:" in result.stdout
        assert "Amount: 1000000" in result.stdout

    def test_json_output(self, registry_available: Path):
        inner = _erc20_approve_calldata(AAVE_POOL, 1_000_000)
        calldata = _safe_exec_calldata(USDC, inner)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
            "--json",
        )
        data = json.loads(result.stdout)
        assert data["intent"] == "sign multisig operation"
        # Registry value drifts ("Safe" → "Safe{Wallet}"); accept any Safe-flavored entity.
        assert "Safe" in data["entity"]
        tx_field = next(f for f in data["fields"] if f["label"] == "Transaction")
        assert "Approve" in tx_field["value"]


class TestSafeAaveSupplyExample:
    """Safe execTransaction wrapping an Aave v3 supply."""

    def test_decodes_nested_supply(self, registry_available: Path):
        inner = _aave_supply_calldata(USDC, 1_000_000, USER)
        calldata = _safe_exec_calldata(AAVE_POOL, inner)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
        )
        assert "Intent: sign multisig operation" in result.stdout
        # Registry value drifts ("Aave" → "Aave DAO"); accept any Aave-flavored entity.
        assert re.search(r"Supply \(Aave[^)]*\)", result.stdout)
        assert "supply(address,uint256,address,uint16)" in result.stdout
        assert "Amount to supply: 1000000" in result.stdout

    def test_json_output(self, registry_available: Path):
        inner = _aave_supply_calldata(USDC, 1_000_000, USER)
        calldata = _safe_exec_calldata(AAVE_POOL, inner)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
            "--json",
        )
        data = json.loads(result.stdout)
        tx_field = next(f for f in data["fields"] if f["label"] == "Transaction")
        assert re.search(r"Supply \(Aave[^)]*\)", tx_field["value"])
        assert "Amount to supply: 1000000" in tx_field["value"]


class TestSafeMultiSendExample:
    """Safe execTransaction via MultiSend — hits schema limits."""

    def test_outer_safe_decodes(self, registry_available: Path):
        approve_data = _erc20_approve_calldata(AAVE_POOL, 1_000_000)
        supply_data = _aave_supply_calldata(USDC, 1_000_000, USER)

        packed = _pack_multisend_tx(0, USDC, 0, approve_data) + _pack_multisend_tx(
            0, AAVE_POOL, 0, supply_data
        )
        multisend_sel = compute_selector("multiSend", ["bytes"])
        multisend_calldata = multisend_sel + encode(["bytes"], [packed])

        calldata = _safe_exec_calldata(MULTISEND, multisend_calldata, operation=1)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
        )
        assert "Intent: sign multisig operation" in result.stdout
        assert "Operation type: Delegate Call" in result.stdout

    def test_multisend_inner_is_raw_hex(self, registry_available: Path):
        """MultiSend packed encoding can't be decoded by ERC-7730 schema."""
        approve_data = _erc20_approve_calldata(AAVE_POOL, 1_000_000)
        supply_data = _aave_supply_calldata(USDC, 1_000_000, USER)

        packed = _pack_multisend_tx(0, USDC, 0, approve_data) + _pack_multisend_tx(
            0, AAVE_POOL, 0, supply_data
        )
        multisend_sel = compute_selector("multiSend", ["bytes"])
        multisend_calldata = multisend_sel + encode(["bytes"], [packed])

        calldata = _safe_exec_calldata(MULTISEND, multisend_calldata, operation=1)

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            SAFE_1_4_1,
            "--registry-path",
            str(registry_available),
            "--from-address",
            USER,
        )
        # The Transaction field should contain raw hex (multiSend not decoded)
        assert "Transaction: 0x8d80ff0a" in result.stdout


class TestUniswapUniversalRouterExample:
    """Uniswap Universal Router — no descriptor in registry."""

    CALLDATA = (
        "0x3593564c000000000000000000000000000000000000000000000000000000000000006"
        "000000000000000000000000000000000000000000000000000000000000000a0000000000"
        "000000000000000000000000000000000000000000000065f5e10000000000000000000000"
        "000000000000000000000000000000000000000000020b000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000020000000000000000000000000000000000000000000000000"
        "000000000000004000000000000000000000000000000000000000000000000000000000000"
        "000a000000000000000000000000000000000000000000000000000000000000000400000000"
        "000000000000000000000000000000000000000000000000000000002000000000000000000"
        "000000000000000000000000000000000016345785d8a00000000000000000000000000000"
        "000000000000000000000000000000000000010000000000000000000000000000000000000"
        "00000000000000000000000000002000000000000000000000000000000000000000000000"
        "000016345785d8a0000000000000000000000000000000000000000000000000000000000"
        "0002faf08000000000000000000000000000000000000000000000000000000000000000a0"
        "000000000000000000000000000000000000000000000000000000000000000100000000000"
        "0000000000000000000000000000000000000000000000000002bc02aaa39b223fe8d0a0e5"
        "c4f27ead9083c756cc20001f4a0b86991c6218b36c1d19d4a2e9eb0ce3606eb4800000000"
        "0000000000000000000000000000000000"
    )

    def test_no_descriptor_found(self, registry_available: Path):
        result = _run_cli(
            "translate",
            self.CALLDATA,
            "--to",
            UNISWAP_ROUTER,
            "--chain-id",
            "1",
            "--registry-path",
            str(registry_available),
            expect_error=True,
        )
        assert result.returncode != 0
        assert "No ERC-7730 descriptor found" in result.stderr
        assert "0x3593564c" in result.stderr


# ── Original tests ───────────────────────────────────────────────────────────


class TestBasicCLI:
    def test_erc20_transfer_human_output(self, registry_available: Path):
        sel = compute_selector("transfer", ["address", "uint256"])
        params = encode(
            ["address", "uint256"],
            ["0x000000000000000000000000000000000000dEaD", 1_000_000_000_000_000_000],
        )
        calldata = "0x" + sel.hex() + params.hex()

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            "0x0000000000000000000000000000000000000001",
            "--chain-id",
            "1",
            "--registry-path",
            str(registry_available),
        )
        assert "Intent: Send" in result.stdout
        assert "Function: transfer(address,uint256)" in result.stdout

    def test_erc20_transfer_json_output(self, registry_available: Path):
        sel = compute_selector("transfer", ["address", "uint256"])
        params = encode(
            ["address", "uint256"],
            ["0x000000000000000000000000000000000000dEaD", 1_000_000_000_000_000_000],
        )
        calldata = "0x" + sel.hex() + params.hex()

        result = _run_cli(
            "translate",
            calldata,
            "--to",
            "0x0000000000000000000000000000000000000001",
            "--chain-id",
            "1",
            "--registry-path",
            str(registry_available),
            "--json",
        )
        data = json.loads(result.stdout)
        assert data["intent"] == "Send"
        assert data["function_name"] == "transfer"
        assert len(data["fields"]) >= 2


class TestCLIErrors:
    def test_missing_to_flag(self):
        result = _run_cli("translate", "0xdeadbeef", expect_error=True)
        assert result.returncode != 0

    def test_unknown_selector(self, registry_available: Path):
        result = _run_cli(
            "translate",
            "0xdeadbeef",
            "--to",
            "0x0000000000000000000000000000000000000001",
            "--registry-path",
            str(registry_available),
            expect_error=True,
        )
        assert result.returncode != 0
        assert "No ERC-7730 descriptor found" in result.stderr

    def test_calldata_too_short(self, registry_available: Path):
        result = _run_cli(
            "translate",
            "0xdead",
            "--to",
            "0x0000000000000000000000000000000000000001",
            "--registry-path",
            str(registry_available),
            expect_error=True,
        )
        assert result.returncode != 0
        assert "too short" in result.stderr


class TestHash:
    def test_hash_outputs_hex_digest(self, tmp_path: Path):
        descriptor = {
            "context": {
                "$id": "Test",
                "contract": {
                    "deployments": [
                        {
                            "chainId": 1,
                            "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                        },
                    ]
                },
            },
            "display": {"formats": {}},
        }
        path = tmp_path / "descriptor.json"
        path.write_text(json.dumps(descriptor))

        result = _run_cli("descriptor-hash", str(path))
        output = result.stdout.strip()
        assert output.startswith("0x")
        assert len(output) == 66
        int(output, 16)

    def test_hash_via_dh_alias(self, tmp_path: Path):
        descriptor = {"context": {"$id": "Test"}, "display": {"formats": {}}}
        path = tmp_path / "descriptor.json"
        path.write_text(json.dumps(descriptor))

        via_full = _run_cli("descriptor-hash", str(path)).stdout.strip()
        via_alias = _run_cli("dh", str(path)).stdout.strip()
        assert via_full == via_alias

    def test_hash_stable_across_whitespace(self, tmp_path: Path):
        """The CLI returns the same hash regardless of input whitespace."""
        descriptor = {"context": {"$id": "Test"}, "display": {"formats": {}}}
        compact_path = tmp_path / "compact.json"
        pretty_path = tmp_path / "pretty.json"
        compact_path.write_text(json.dumps(descriptor, separators=(",", ":")))
        pretty_path.write_text(json.dumps(descriptor, indent=2))

        compact = _run_cli("descriptor-hash", str(compact_path)).stdout.strip()
        pretty = _run_cli("descriptor-hash", str(pretty_path)).stdout.strip()
        assert compact == pretty

    def test_hash_missing_file(self):
        result = _run_cli("descriptor-hash", "/nonexistent/descriptor.json", expect_error=True)
        assert result.returncode != 0
        assert "Error" in result.stderr


class TestCalldataEncoding:
    APPROVE_HEX = (
        "0x095ea7b3"
        "00000000000000000000000005c54380408ab9c31157b7563138f798f7826aa0"
        "0000000000000000000000000000000000000000000000000000000000000001"
    )

    def test_calldata_command(self):
        result = _run_cli(
            "calldata",
            "approve(address,uint256)",
            "0x05C54380408aB9c31157B7563138F798f7826aA0",
            "1",
        )
        assert result.stdout.strip() == self.APPROVE_HEX

    def test_calldata_cd_alias(self):
        result = _run_cli(
            "cd",
            "approve(address,uint256)",
            "0x05C54380408aB9c31157B7563138F798f7826aA0",
            "1",
        )
        assert result.stdout.strip() == self.APPROVE_HEX

    def test_calldata_wrong_arg_count(self):
        result = _run_cli(
            "calldata",
            "approve(address,uint256)",
            "0x05C54380408aB9c31157B7563138F798f7826aA0",
            expect_error=True,
        )
        assert result.returncode != 0
        assert "Error" in result.stderr


class TestSig:
    def test_approve_selector(self):
        result = _run_cli("sig", "approve(address,uint256)")
        assert result.stdout.strip() == "0x095ea7b3"

    def test_transfer_selector(self):
        result = _run_cli("sig", "transfer(address,uint256)")
        assert result.stdout.strip() == "0xa9059cbb"

    def test_no_args(self):
        result = _run_cli("sig", "pause()")
        assert result.stdout.strip().startswith("0x")
        assert len(result.stdout.strip()) == 10


class TestCalldataDigestCdgAlias:
    def test_cdg_alias_matches_full_name(self):
        calldata = "0xa9059cbb"
        via_full = _run_cli("calldata-digest", calldata).stdout.strip()
        via_alias = _run_cli("cdg", calldata).stdout.strip()
        assert via_full == via_alias


APPROVE_CALLDATA = (
    "0x095ea7b3"
    "00000000000000000000000005c54380408ab9c31157b7563138f798f7826aa0"
    "0000000000000000000000000000000000000000000000000000000000000001"
)


class TestCalldataDecode:
    def test_decodes_human(self):
        result = _run_cli("calldata-decode", "approve(address,uint256)", APPROVE_CALLDATA)
        lines = result.stdout.strip().splitlines()
        assert lines[0].lower() == "0x05c54380408ab9c31157b7563138f798f7826aa0"
        assert lines[1] == "1"

    def test_decodes_json(self):
        result = _run_cli("calldata-decode", "approve(address,uint256)", APPROVE_CALLDATA, "--json")
        data = json.loads(result.stdout)
        assert data["function"] == "approve"
        assert data["args"][0].lower() == "0x05c54380408ab9c31157b7563138f798f7826aa0"
        assert data["args"][1] == "1"

    def test_selector_mismatch_errors(self):
        result = _run_cli(
            "calldata-decode",
            "transfer(address,uint256)",
            APPROVE_CALLDATA,
            expect_error=True,
        )
        assert result.returncode != 0
        assert "selector mismatch" in result.stderr


class TestKeccak:
    def test_hashes_string(self):
        # keccak256("approve(address,uint256)") begins with the approve selector
        result = _run_cli("keccak", "approve(address,uint256)")
        assert result.stdout.strip().startswith("0x095ea7b3")

    def test_hashes_hex_bytes(self):
        # keccak256(b"") — the empty-bytes hash
        result = _run_cli("keccak", "0x")
        assert result.stdout.strip() == (
            "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        )

    def test_string_flag_forces_utf8_mode(self):
        # Without --string, "0x" hashes as empty bytes. With --string, hash UTF-8 "0x".
        hex_mode = _run_cli("keccak", "0x").stdout.strip()
        str_mode = _run_cli("keccak", "0x", "--string").stdout.strip()
        assert hex_mode != str_mode
