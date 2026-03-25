from eth_abi import encode

from erc7730._abi import (
    canonical_type,
    compute_selector,
    decode_calldata,
    function_selector,
    hex_to_bytes,
    parse_display_signature,
)


class TestCanonicalType:
    def test_simple_types(self):
        assert canonical_type({"type": "address"}) == "address"
        assert canonical_type({"type": "uint256"}) == "uint256"
        assert canonical_type({"type": "bool"}) == "bool"
        assert canonical_type({"type": "bytes32"}) == "bytes32"
        assert canonical_type({"type": "string"}) == "string"

    def test_array_type(self):
        assert canonical_type({"type": "address[]"}) == "address[]"
        assert canonical_type({"type": "uint256[3]"}) == "uint256[3]"

    def test_tuple_type(self):
        abi_input = {
            "type": "tuple",
            "components": [
                {"type": "uint16"},
                {"type": "uint16"},
                {"type": "string"},
            ],
        }
        assert canonical_type(abi_input) == "(uint16,uint16,string)"

    def test_tuple_array_type(self):
        abi_input = {
            "type": "tuple[]",
            "components": [
                {"type": "address"},
                {"type": "uint256"},
            ],
        }
        assert canonical_type(abi_input) == "(address,uint256)[]"

    def test_nested_tuple_type(self):
        abi_input = {
            "type": "tuple",
            "components": [
                {"type": "address"},
                {
                    "type": "tuple",
                    "components": [
                        {"type": "uint256"},
                        {"type": "bool"},
                    ],
                },
            ],
        }
        assert canonical_type(abi_input) == "(address,(uint256,bool))"


class TestComputeSelector:
    def test_erc20_transfer(self):
        sel = compute_selector("transfer", ["address", "uint256"])
        assert sel.hex() == "a9059cbb"

    def test_erc20_approve(self):
        sel = compute_selector("approve", ["address", "uint256"])
        assert sel.hex() == "095ea7b3"

    def test_erc20_transfer_from(self):
        sel = compute_selector("transferFrom", ["address", "address", "uint256"])
        assert sel.hex() == "23b872dd"

    def test_aave_supply(self):
        sel = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        assert sel.hex() == "617ba037"


class TestFunctionSelector:
    def test_from_abi_inputs(self):
        inputs = [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ]
        sel = function_selector("transfer", inputs)
        assert sel.hex() == "a9059cbb"

    def test_with_tuple_input(self):
        inputs = [
            {"name": "id", "type": "uint8"},
            {
                "name": "category",
                "type": "tuple",
                "components": [
                    {"name": "ltv", "type": "uint16"},
                    {"name": "liquidationThreshold", "type": "uint16"},
                    {"name": "liquidationBonus", "type": "uint16"},
                    {"name": "label", "type": "string"},
                ],
            },
        ]
        sel = function_selector("configureEModeCategory", inputs)
        # Selector for configureEModeCategory(uint8,(uint16,uint16,uint16,string))
        expected = compute_selector(
            "configureEModeCategory", ["uint8", "(uint16,uint16,uint16,string)"]
        )
        assert sel == expected


class TestDecodeCalldata:
    def test_decode_address_uint256(self):
        encoded = encode(
            ["address", "uint256"],
            ["0x000000000000000000000000000000000000dEaD", 42],
        )
        result = decode_calldata(["address", "uint256"], encoded)
        assert result[0].lower() == "0x000000000000000000000000000000000000dead"
        assert result[1] == 42

    def test_decode_bool(self):
        encoded = encode(["bool"], [True])
        result = decode_calldata(["bool"], encoded)
        assert result[0] is True

    def test_decode_bytes(self):
        encoded = encode(["bytes"], [b"\x01\x02\x03"])
        result = decode_calldata(["bytes"], encoded)
        assert result[0] == b"\x01\x02\x03"


class TestParseDisplaySignature:
    def test_simple_no_names(self):
        name, types = parse_display_signature("transfer(address,uint256)")
        assert name == "transfer"
        assert types == ["address", "uint256"]

    def test_with_param_names(self):
        name, types = parse_display_signature(
            "repay(address asset, uint256 amount, uint256 interestRateMode, address onBehalfOf)"
        )
        assert name == "repay"
        assert types == ["address", "uint256", "uint256", "address"]

    def test_no_params(self):
        name, types = parse_display_signature("pause()")
        assert name == "pause"
        assert types == []

    def test_safe_exec_transaction(self):
        sig = (
            "execTransaction(address to, uint256 value, bytes data, "
            "uint8 operation, uint256 safeTxGas, uint256 baseGas, "
            "uint256 gasPrice, address gasToken, address refundReceiver, "
            "bytes signatures)"
        )
        name, types = parse_display_signature(sig)
        assert name == "execTransaction"
        assert types == [
            "address", "uint256", "bytes", "uint8",
            "uint256", "uint256", "uint256", "address",
            "address", "bytes",
        ]

    def test_array_params(self):
        name, types = parse_display_signature(
            "setup(address[] _owners, uint256 _threshold)"
        )
        assert name == "setup"
        assert types == ["address[]", "uint256"]


class TestHexToBytes:
    def test_with_prefix(self):
        result = hex_to_bytes("0xabcd")
        assert result == b"\xab\xcd"

    def test_without_prefix(self):
        result = hex_to_bytes("abcd")
        assert result == b"\xab\xcd"

    def test_uppercase_prefix(self):
        result = hex_to_bytes("0XABCD")
        assert result == b"\xab\xcd"
