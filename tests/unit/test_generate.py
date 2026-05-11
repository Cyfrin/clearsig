"""Unit tests for the generator (clearsig/_generate.py)."""

from __future__ import annotations

import pytest

from clearsig._generate import (
    ArrayNode,
    LeafNode,
    StructNode,
    _component_to_tree,
    _pick_format,
    _strip_array_suffixes,
    _to_title,
    generate_descriptor,
)


class TestStripArraySuffixes:
    def test_no_array(self) -> None:
        assert _strip_array_suffixes("uint256") == ("uint256", 0)

    def test_single_array(self) -> None:
        assert _strip_array_suffixes("uint256[]") == ("uint256", 1)

    def test_fixed_size_array(self) -> None:
        assert _strip_array_suffixes("address[5]") == ("address", 1)

    def test_multi_dim(self) -> None:
        assert _strip_array_suffixes("uint256[][3]") == ("uint256", 2)

    def test_tuple_array(self) -> None:
        assert _strip_array_suffixes("tuple[]") == ("tuple", 1)


class TestComponentToTree:
    def test_scalar_leaf(self) -> None:
        node = _component_to_tree({"name": "x", "type": "uint256"})
        assert node == LeafNode(data_type="uint")

    def test_address(self) -> None:
        node = _component_to_tree({"name": "to", "type": "address"})
        assert node == LeafNode(data_type="address")

    def test_dynamic_bytes_normalizes_to_bytes(self) -> None:
        node = _component_to_tree({"name": "data", "type": "bytes"})
        assert node == LeafNode(data_type="bytes")

    def test_fixed_bytes_normalizes_to_bytes(self) -> None:
        node = _component_to_tree({"name": "h", "type": "bytes32"})
        assert node == LeafNode(data_type="bytes")

    def test_array_of_scalar(self) -> None:
        node = _component_to_tree({"name": "xs", "type": "uint256[]"})
        assert node == ArrayNode(element=LeafNode(data_type="uint"))

    def test_struct(self) -> None:
        node = _component_to_tree(
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "a", "type": "uint256"},
                    {"name": "b", "type": "address"},
                ],
            }
        )
        assert isinstance(node, StructNode)
        assert node.components["a"] == LeafNode(data_type="uint")
        assert node.components["b"] == LeafNode(data_type="address")

    def test_array_of_struct(self) -> None:
        node = _component_to_tree(
            {
                "name": "calls",
                "type": "tuple[]",
                "components": [{"name": "target", "type": "address"}],
            }
        )
        assert isinstance(node, ArrayNode)
        assert isinstance(node.element, StructNode)


class TestPickFormat:
    @pytest.mark.parametrize(
        "name,data_type,expected_format,expected_params",
        [
            # uint heuristics
            ("amount", "uint", "amount", None),
            ("value", "uint", "amount", None),
            ("price", "uint", "amount", None),
            ("deadline", "uint", "date", {"encoding": "timestamp"}),
            ("expirationTime", "uint", "date", {"encoding": "timestamp"}),
            ("blockHeight", "uint", "date", {"encoding": "blockheight"}),
            ("duration", "uint", "duration", None),
            ("nonce", "uint", "raw", None),
            # address heuristics
            ("spender", "address", "addressName", {"types": ["contract"]}),
            ("asset", "address", "addressName", {"types": ["token"]}),
            ("token", "address", "addressName", {"types": ["token"]}),
            ("to", "address", "addressName", {"types": ["eoa", "wallet"]}),
            ("from", "address", "addressName", {"types": ["eoa", "wallet"]}),
            ("recipient", "address", "addressName", {"types": ["eoa", "wallet"]}),
            ("nftCollection", "address", "nftName", {"types": ["collection"]}),
            # bytes heuristics
            ("calldata", "bytes", "calldata", None),
            ("data", "bytes", "raw", None),
            # fallback
            ("flag", "bool", "raw", None),
            ("name", "string", "raw", None),
        ],
    )
    def test_heuristics(
        self,
        name: str,
        data_type: str,
        expected_format: str,
        expected_params: dict | None,
    ) -> None:
        fmt, params = _pick_format(name, data_type)
        assert fmt == expected_format
        assert params == expected_params

    def test_unknown_address_falls_back_to_all_types(self) -> None:
        fmt, params = _pick_format("addr", "address")
        assert fmt == "addressName"
        assert params is not None
        assert set(params["types"]) == {"wallet", "eoa", "contract", "token", "collection"}


class TestToTitle:
    def test_snake_case(self) -> None:
        assert _to_title("amount_in") == "Amount In"

    def test_camel_case(self) -> None:
        assert _to_title("amountIn") == "Amount In"

    def test_leading_underscore(self) -> None:
        assert _to_title("_amount") == "Amount"

    def test_single_word(self) -> None:
        assert _to_title("to") == "To"

    def test_empty(self) -> None:
        assert _to_title("") == ""


class TestGenerateDescriptor:
    ERC20_ABI = [
        {
            "type": "function",
            "name": "transfer",
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "outputs": [{"type": "bool"}],
        },
        {
            "type": "function",
            "name": "approve",
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "outputs": [{"type": "bool"}],
        },
        {
            "type": "event",  # should be filtered out
            "name": "Transfer",
            "inputs": [],
        },
    ]

    def test_descriptor_shape(self) -> None:
        d = generate_descriptor(
            chain_id=1,
            contract_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            abi=self.ERC20_ABI,
            owner="USDC",
        )
        assert "$schema" in d
        assert d["context"]["contract"]["deployments"] == [
            {"chainId": 1, "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}
        ]
        assert d["metadata"]["owner"] == "USDC"
        # Only function entries make it into the descriptor's ABI
        assert all(e["type"] == "function" for e in d["context"]["contract"]["abi"])
        # Both functions get format entries with the canonical signature
        formats = d["display"]["formats"]
        assert set(formats.keys()) == {
            "transfer(address,uint256)",
            "approve(address,uint256)",
        }

    def test_transfer_fields(self) -> None:
        d = generate_descriptor(
            chain_id=1,
            contract_address="0x0000000000000000000000000000000000000000",
            abi=self.ERC20_ABI,
        )
        fields = d["display"]["formats"]["transfer(address,uint256)"]["fields"]
        assert fields == [
            {
                "path": "to",
                "label": "To",
                "format": "addressName",
                "params": {"types": ["eoa", "wallet"]},
            },
            {"path": "amount", "label": "Amount", "format": "amount"},
        ]

    def test_v2_changes_schema_url(self) -> None:
        v1 = generate_descriptor(
            chain_id=1, contract_address="0x0", abi=self.ERC20_ABI, schema_version="v1"
        )
        v2 = generate_descriptor(
            chain_id=1, contract_address="0x0", abi=self.ERC20_ABI, schema_version="v2"
        )
        assert "v1.schema.json" in v1["$schema"]
        assert "v2.schema.json" in v2["$schema"]
        # Body otherwise identical
        assert v1["display"] == v2["display"]
        assert v1["context"] == v2["context"]

    def test_legal_name_requires_url(self) -> None:
        d = generate_descriptor(
            chain_id=1,
            contract_address="0x0",
            abi=[],
            owner="Circle",
            legal_name="Circle Internet Financial",
            # no url → info should not be set
        )
        assert d["metadata"]["owner"] == "Circle"
        assert "info" not in d["metadata"]

    def test_legal_name_with_url_sets_info(self) -> None:
        d = generate_descriptor(
            chain_id=1,
            contract_address="0x0",
            abi=[],
            legal_name="Circle Internet Financial",
            url="https://circle.com",
        )
        assert d["metadata"]["info"] == {
            "legalName": "Circle Internet Financial",
            "url": "https://circle.com",
        }


class TestNestedStructs:
    def test_array_of_struct_produces_nested_fields(self) -> None:
        abi = [
            {
                "type": "function",
                "name": "processOrders",
                "inputs": [
                    {
                        "name": "orders",
                        "type": "tuple[]",
                        "components": [
                            {"name": "token", "type": "address"},
                            {"name": "amount", "type": "uint256"},
                            {"name": "recipient", "type": "address"},
                        ],
                    }
                ],
            }
        ]
        d = generate_descriptor(chain_id=1, contract_address="0x0", abi=abi)
        fields = d["display"]["formats"]["processOrders((address,uint256,address)[])"]["fields"]
        assert len(fields) == 1
        outer = fields[0]
        assert outer["path"] == "orders.[]"
        assert "fields" in outer
        inner_paths = [f["path"] for f in outer["fields"]]
        assert inner_paths == ["token", "amount", "recipient"]

    def test_multidim_array_of_scalar(self) -> None:
        abi = [
            {
                "type": "function",
                "name": "process2D",
                "inputs": [{"name": "matrix", "type": "uint256[][]"}],
            }
        ]
        d = generate_descriptor(chain_id=1, contract_address="0x0", abi=abi)
        fields = d["display"]["formats"]["process2D(uint256[][])"]["fields"]
        assert fields == [{"path": "matrix.[].[]", "label": "Matrix", "format": "raw"}]

    def test_nested_struct(self) -> None:
        abi = [
            {
                "type": "function",
                "name": "deposit",
                "inputs": [
                    {
                        "name": "params",
                        "type": "tuple",
                        "components": [
                            {"name": "asset", "type": "address"},
                            {"name": "amount", "type": "uint256"},
                        ],
                    }
                ],
            }
        ]
        d = generate_descriptor(chain_id=1, contract_address="0x0", abi=abi)
        fields = d["display"]["formats"]["deposit((address,uint256))"]["fields"]
        # Nested struct emits a nestedFields entry, not flattened
        assert len(fields) == 1
        assert fields[0]["path"] == "params"
        inner = fields[0]["fields"]
        assert [f["path"] for f in inner] == ["asset", "amount"]
