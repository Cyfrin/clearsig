import json
import tempfile
from pathlib import Path

from erc7730._abi import compute_selector
from erc7730._registry import Registry


def _make_registry(descriptors: dict[str, dict], ercs: dict[str, dict] | None = None) -> Registry:
    """Create a Registry from in-memory descriptor dicts in a temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        if descriptors:
            for entity_path, descriptor in descriptors.items():
                parts = entity_path.split("/")
                entity = parts[0]
                filename = parts[1]
                entity_dir = root / "registry" / entity
                entity_dir.mkdir(parents=True, exist_ok=True)
                (entity_dir / filename).write_text(json.dumps(descriptor))

        if ercs:
            ercs_dir = root / "ercs"
            ercs_dir.mkdir(parents=True, exist_ok=True)
            for filename, descriptor in ercs.items():
                (ercs_dir / filename).write_text(json.dumps(descriptor))

        return Registry.from_path(root)


ERC20_DESCRIPTOR = {
    "context": {
        "contract": {
            "abi": [
                {
                    "type": "function",
                    "name": "transfer",
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"},
                    ],
                },
            ],
        }
    },
    "display": {
        "formats": {
            "transfer(address,uint256)": {
                "intent": "Send",
                "fields": [
                    {"path": "_value", "label": "Amount", "format": "raw"},
                    {"path": "_to", "label": "To", "format": "addressName"},
                ],
            }
        }
    },
}

AAVE_DESCRIPTOR = {
    "context": {
        "contract": {
            "deployments": [
                {"chainId": 1, "address": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"},
            ],
            "abi": [
                {
                    "type": "function",
                    "name": "supply",
                    "inputs": [
                        {"name": "asset", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "onBehalfOf", "type": "address"},
                        {"name": "referralCode", "type": "uint16"},
                    ],
                },
            ],
        }
    },
    "metadata": {"owner": "Aave"},
    "display": {
        "formats": {
            "supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode)": {
                "intent": "Supply",
                "fields": [
                    {
                        "path": "amount",
                        "format": "tokenAmount",
                        "label": "Amount to supply",
                        "params": {"tokenPath": "asset"},
                    },
                ],
            }
        }
    },
}


class TestRegistryFromPath:
    def test_loads_erc_generic_descriptor(self):
        registry = _make_registry({}, ercs={"calldata-erc20.json": ERC20_DESCRIPTOR})
        sel = compute_selector("transfer", ["address", "uint256"])
        func = registry.lookup(sel, 1, "0x0000000000000000000000000000000000000001")
        assert func is not None
        assert func.display["intent"] == "Send"

    def test_loads_entity_descriptor_with_deployment(self):
        registry = _make_registry({"aave/calldata-lpv3.json": AAVE_DESCRIPTOR})
        sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        func = registry.lookup(sel, 1, "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")
        assert func is not None
        assert func.display["intent"] == "Supply"
        assert func.entity == "Aave"  # from metadata.owner

    def test_deployment_lookup_wrong_address_falls_back_to_generic(self):
        registry = _make_registry(
            {"aave/calldata-lpv3.json": AAVE_DESCRIPTOR},
            ercs={"calldata-erc20.json": ERC20_DESCRIPTOR},
        )
        # supply won't match ERC20 generic, so lookup on wrong address returns None
        sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        func = registry.lookup(sel, 1, "0x0000000000000000000000000000000000000001")
        assert func is None

    def test_deployment_lookup_wrong_chain_returns_none(self):
        registry = _make_registry({"aave/calldata-lpv3.json": AAVE_DESCRIPTOR})
        sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        func = registry.lookup(sel, 999, "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")
        assert func is None

    def test_case_insensitive_address_lookup(self):
        registry = _make_registry({"aave/calldata-lpv3.json": AAVE_DESCRIPTOR})
        sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        func = registry.lookup(sel, 1, "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2")
        assert func is not None


class TestRegistryWithIncludes:
    def test_includes_merges_common_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            entity_dir = root / "registry" / "safe"
            entity_dir.mkdir(parents=True)

            common = {
                "metadata": {
                    "owner": "Safe",
                    "enums": {"operation": {"0": "Call", "1": "Delegate Call"}},
                },
                "display": {
                    "formats": {
                        "changeThreshold(uint256 _threshold)": {
                            "intent": "Modify threshold",
                            "fields": [
                                {"path": "_threshold", "label": "New threshold", "format": "raw"}
                            ],
                        }
                    }
                },
            }
            (entity_dir / "common-Safe.json").write_text(json.dumps(common))

            descriptor = {
                "includes": "common-Safe.json",
                "context": {
                    "contract": {
                        "deployments": [{"chainId": 1, "address": "0xABCD"}],
                        "abi": [
                            {
                                "type": "function",
                                "name": "changeThreshold",
                                "inputs": [{"name": "_threshold", "type": "uint256"}],
                            }
                        ],
                    }
                },
            }
            (entity_dir / "calldata-Safe.json").write_text(json.dumps(descriptor))

            registry = Registry.from_path(root)
            sel = compute_selector("changeThreshold", ["uint256"])
            func = registry.lookup(sel, 1, "0xabcd")
            assert func is not None
            assert func.display["intent"] == "Modify threshold"
            assert func.entity == "Safe"


class TestRegistryWithUrlAbi:
    def test_synthesizes_from_display_key_when_abi_is_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            entity_dir = root / "registry" / "test"
            entity_dir.mkdir(parents=True)

            descriptor = {
                "context": {
                    "contract": {
                        "abi": "https://example.com/abi.json",
                        "deployments": [{"chainId": 1, "address": "0xBEEF"}],
                    }
                },
                "display": {
                    "formats": {
                        "doSomething(address target, uint256 amount)": {
                            "intent": "Do Something",
                            "fields": [
                                {"path": "amount", "label": "Amount", "format": "raw"}
                            ],
                        }
                    }
                },
            }
            (entity_dir / "calldata-Test.json").write_text(json.dumps(descriptor))

            registry = Registry.from_path(root)
            sel = compute_selector("doSomething", ["address", "uint256"])
            func = registry.lookup(sel, 1, "0xbeef")
            assert func is not None
            assert func.name == "doSomething"
            assert func.input_names == ["target", "amount"]
            assert func.input_types == ["address", "uint256"]
