from clearsig._formatter import (
    _format_address,
    _format_enum,
    _format_raw,
    _format_token_amount,
    _format_unit,
    _resolve_metadata_ref,
    format_fields,
)


class TestFormatRaw:
    def test_int(self):
        assert _format_raw(42) == "42"

    def test_bool(self):
        assert _format_raw(True) == "True"
        assert _format_raw(False) == "False"

    def test_string(self):
        assert _format_raw("hello") == "hello"

    def test_bytes(self):
        assert _format_raw(b"\xab\xcd") == "0xabcd"


class TestFormatAddress:
    def test_string_address(self):
        addr = "0x000000000000000000000000000000000000dEaD"
        assert _format_address(addr) == addr

    def test_bytes_address(self):
        addr_bytes = bytes.fromhex("000000000000000000000000000000000000dead")
        assert _format_address(addr_bytes) == "0x000000000000000000000000000000000000dead"


class TestFormatTokenAmount:
    def test_normal_amount(self):
        result = _format_token_amount(1000, {}, {})
        assert result == "1000"

    def test_above_threshold_unlimited(self):
        params = {
            "threshold": "0x8000000000000000000000000000000000000000000000000000000000000000",
        }
        huge = int("0x" + "f" * 64, 16)
        result = _format_token_amount(huge, params, {})
        assert result == "Unlimited"

    def test_above_threshold_custom_message(self):
        params = {
            "threshold": "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "message": "All",
        }
        max_uint = 2**256 - 1
        result = _format_token_amount(max_uint, params, {})
        assert result == "All"

    def test_below_threshold(self):
        params = {
            "threshold": "0x8000000000000000000000000000000000000000000000000000000000000000",
        }
        result = _format_token_amount(100, params, {})
        assert result == "100"

    def test_threshold_from_metadata_ref(self):
        params = {"threshold": "$.metadata.constants.max", "message": "All"}
        metadata = {
            "constants": {
                "max": "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
            }
        }
        max_uint = 2**256 - 1
        result = _format_token_amount(max_uint, params, metadata)
        assert result == "All"


class TestFormatEnum:
    def test_direct_enum(self):
        params = {"0": "none", "1": "deprecated", "2": "variable"}
        assert _format_enum(2, params, {}) == "variable"

    def test_enum_with_ref(self):
        params = {"$ref": "$.metadata.enums.interestRateMode"}
        metadata = {
            "enums": {"interestRateMode": {"0": "none", "1": "deprecated", "2": "variable"}}
        }
        assert _format_enum(2, params, metadata) == "variable"

    def test_enum_unknown_value(self):
        params = {"0": "none", "1": "deprecated"}
        assert _format_enum(99, params, {}) == "99"


class TestFormatUnit:
    def test_percentage(self):
        result = _format_unit(3000, {"decimals": 4, "base": "%"})
        assert result == "0.3%"

    def test_no_decimals(self):
        result = _format_unit(42, {"base": " gwei"})
        assert result == "42 gwei"


class TestResolveMetadataRef:
    def test_resolves_nested_path(self):
        metadata = {"constants": {"max": "0xff"}}
        assert _resolve_metadata_ref("$.metadata.constants.max", metadata) == "0xff"

    def test_non_ref_passthrough(self):
        assert _resolve_metadata_ref("plain_value", {}) == "plain_value"

    def test_missing_path(self):
        assert _resolve_metadata_ref("$.metadata.missing.key", {}) == "$.metadata.missing.key"


class TestFormatFields:
    def test_erc20_transfer_fields(self):
        display = {
            "intent": "Send",
            "fields": [
                {"path": "_value", "label": "Amount", "format": "raw"},
                {"path": "_to", "label": "To", "format": "addressName"},
            ],
        }
        decoded = {"_value": 1000, "_to": "0xdead"}
        result = format_fields(display, decoded, {})
        assert len(result) == 2
        assert result[0].label == "Amount"
        assert result[0].value == "1000"
        assert result[1].label == "To"
        assert result[1].value == "0xdead"

    def test_transaction_context_fields(self):
        display = {
            "fields": [
                {"path": "@.from", "label": "Sender", "format": "addressName"},
                {"path": "@.to", "label": "Contract", "format": "addressName"},
            ],
        }
        tx_context = {"from": "0xsender", "to": "0xcontract"}
        result = format_fields(display, {}, {}, tx_context)
        assert result[0].value == "0xsender"
        assert result[1].value == "0xcontract"

    def test_enum_field_with_ref(self):
        display = {
            "fields": [
                {
                    "path": "operation",
                    "label": "Operation type",
                    "format": "enum",
                    "params": {"$ref": "$.metadata.enums.operation"},
                },
            ],
        }
        metadata = {"enums": {"operation": {"0": "Call", "1": "Delegate Call"}}}
        result = format_fields(display, {"operation": 0}, metadata)
        assert result[0].value == "Call"
