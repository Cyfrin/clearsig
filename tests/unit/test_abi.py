import pytest
from eth_abi import encode

from clearsig._abi import (
    canonical_type,
    compute_selector,
    decode_calldata,
    decode_calldata_with_signature,
    encode_calldata,
    encode_calldata_hex,
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
        ]

    def test_array_params(self):
        name, types = parse_display_signature("setup(address[] _owners, uint256 _threshold)")
        assert name == "setup"
        assert types == ["address[]", "uint256"]


class TestEncodeCalldata:
    APPROVE_HEX = (
        "0x095ea7b3"
        "00000000000000000000000005c54380408ab9c31157b7563138f798f7826aa0"
        "0000000000000000000000000000000000000000000000000000000000000001"
    )

    def test_approve(self):
        result = encode_calldata_hex(
            "approve(address,uint256)",
            ["0x05C54380408aB9c31157B7563138F798f7826aA0", "1"],
        )
        assert result == self.APPROVE_HEX

    def test_returns_bytes(self):
        result = encode_calldata(
            "approve(address,uint256)",
            ["0x05C54380408aB9c31157B7563138F798f7826aA0", "1"],
        )
        assert isinstance(result, bytes)
        assert "0x" + result.hex() == self.APPROVE_HEX

    def test_hex_uint_arg(self):
        result = encode_calldata_hex(
            "approve(address,uint256)",
            ["0x05C54380408aB9c31157B7563138F798f7826aA0", "0xff"],
        )
        assert result.endswith("00" * 31 + "ff")

    def test_bool_arg(self):
        result = encode_calldata_hex("setApproved(bool)", ["true"])
        assert result.endswith("01")

    def test_string_arg(self):
        result = encode_calldata_hex("greet(string)", ["hi"])
        # selector for greet(string)
        assert result.startswith("0x" + compute_selector("greet", ["string"]).hex())

    def test_array_arg(self):
        result = encode_calldata_hex("set(uint256[])", ["[1,2,3]"])
        assert result.startswith("0x" + compute_selector("set", ["uint256[]"]).hex())

    def test_no_args(self):
        result = encode_calldata_hex("pause()", [])
        assert result == "0x" + compute_selector("pause", []).hex()

    def test_wrong_arg_count(self):
        with pytest.raises(ValueError, match="expects 2 argument"):
            encode_calldata("approve(address,uint256)", ["0x0"])

    def test_unsupported_type(self):
        with pytest.raises(ValueError, match="unsupported ABI type"):
            encode_calldata("f(weirdtype)", ["x"])


class TestDecodeCalldataWithSignature:
    APPROVE_HEX = (
        "0x095ea7b3"
        "00000000000000000000000005c54380408ab9c31157b7563138f798f7826aa0"
        "0000000000000000000000000000000000000000000000000000000000000001"
    )

    def test_roundtrip(self):
        name, types, values = decode_calldata_with_signature(
            "approve(address,uint256)", self.APPROVE_HEX
        )
        assert name == "approve"
        assert types == ["address", "uint256"]
        assert values[0].lower() == "0x05c54380408ab9c31157b7563138f798f7826aa0"
        assert values[1] == 1

    def test_selector_mismatch_raises(self):
        with pytest.raises(ValueError, match="selector mismatch"):
            decode_calldata_with_signature("transfer(address,uint256)", self.APPROVE_HEX)

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            decode_calldata_with_signature("approve(address,uint256)", "0xabcd")


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

    def test_rejects_odd_length(self):
        with pytest.raises(ValueError, match="even number"):
            hex_to_bytes("0xabc")

    def test_rejects_odd_length_no_prefix(self):
        with pytest.raises(ValueError, match="even number"):
            hex_to_bytes("abc")
