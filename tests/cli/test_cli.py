"""CLI tests that invoke the erc7730 command as a subprocess."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eth_abi import encode
from erc7730._abi import compute_selector

REGISTRY_PATH = Path(__file__).parent.parent.parent / "clear-signing-erc7730-registry"


@pytest.fixture()
def registry_available() -> Path:
    if not REGISTRY_PATH.exists():
        pytest.skip("Local registry not available")
    return REGISTRY_PATH


def _run_cli(*args: str, expect_error: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, "-m", "erc7730", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not expect_error:
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return result


def _erc20_transfer_calldata() -> str:
    selector = compute_selector("transfer", ["address", "uint256"])
    params = encode(
        ["address", "uint256"],
        ["0x000000000000000000000000000000000000dEaD", 1_000_000_000_000_000_000],
    )
    return "0x" + selector.hex() + params.hex()


class TestTranslateCommand:
    def test_human_output(self, registry_available: Path):
        calldata = _erc20_transfer_calldata()
        result = _run_cli(
            "translate", calldata,
            "--to", "0x0000000000000000000000000000000000000001",
            "--chain-id", "1",
            "--registry-path", str(registry_available),
        )
        assert "Intent: Send" in result.stdout
        assert "Function: transfer(address,uint256)" in result.stdout
        assert "Amount:" in result.stdout
        assert "To:" in result.stdout

    def test_json_output(self, registry_available: Path):
        calldata = _erc20_transfer_calldata()
        result = _run_cli(
            "translate", calldata,
            "--to", "0x0000000000000000000000000000000000000001",
            "--chain-id", "1",
            "--registry-path", str(registry_available),
            "--json",
        )
        data = json.loads(result.stdout)
        assert data["intent"] == "Send"
        assert data["function_name"] == "transfer"
        assert len(data["fields"]) >= 2

    def test_aave_supply_json(self, registry_available: Path):
        selector = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        params = encode(
            ["address", "uint256", "address", "uint16"],
            [
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1_000_000,
                "0x000000000000000000000000000000000000dEaD",
                0,
            ],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = _run_cli(
            "translate", calldata,
            "--to", "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            "--chain-id", "1",
            "--registry-path", str(registry_available),
            "--json",
        )
        data = json.loads(result.stdout)
        assert data["intent"] == "Supply"

    def test_from_address_flag(self, registry_available: Path):
        selector = compute_selector(
            "execTransaction",
            [
                "address", "uint256", "bytes", "uint8",
                "uint256", "uint256", "uint256",
                "address", "address", "bytes",
            ],
        )
        params = encode(
            [
                "address", "uint256", "bytes", "uint8",
                "uint256", "uint256", "uint256",
                "address", "address", "bytes",
            ],
            [
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                0, b"", 0, 0, 0, 0,
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                b"",
            ],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = _run_cli(
            "translate", calldata,
            "--to", "0x41675C099F32341bf84BFc5382aF534df5C7461a",
            "--registry-path", str(registry_available),
            "--from-address", "0xABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD",
            "--json",
        )
        data = json.loads(result.stdout)
        signer = next(f for f in data["fields"] if f["label"] == "Execution signer")
        assert signer["value"] == "0xABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"


class TestCLIErrors:
    def test_missing_to_flag(self):
        result = _run_cli("translate", "0xdeadbeef", expect_error=True)
        assert result.returncode != 0

    def test_unknown_selector(self, registry_available: Path):
        result = _run_cli(
            "translate", "0xdeadbeef",
            "--to", "0x0000000000000000000000000000000000000001",
            "--registry-path", str(registry_available),
            expect_error=True,
        )
        assert result.returncode != 0
        assert "No ERC-7730 descriptor found" in result.stderr

    def test_calldata_too_short(self, registry_available: Path):
        result = _run_cli(
            "translate", "0xdead",
            "--to", "0x0000000000000000000000000000000000000001",
            "--registry-path", str(registry_available),
            expect_error=True,
        )
        assert result.returncode != 0
        assert "too short" in result.stderr
