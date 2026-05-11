"""Unit tests for the descriptor hashing module."""

import json

import pytest

from clearsig import descriptor_hash, descriptor_hash_hex

SAMPLE_DESCRIPTOR = {
    "context": {
        "$id": "Test",
        "contract": {
            "deployments": [
                {"chainId": 1, "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"},
            ]
        },
    },
    "display": {
        "formats": {
            "transfer(address to,uint256 value)": {
                "intent": "Send",
                "fields": [{"path": "to", "label": "To", "format": "addressName"}],
            }
        }
    },
}


class TestDescriptorHash:
    def test_returns_32_bytes(self):
        result = descriptor_hash(SAMPLE_DESCRIPTOR)
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_hex_output_format(self):
        result = descriptor_hash_hex(SAMPLE_DESCRIPTOR)
        assert result.startswith("0x")
        assert len(result) == 66  # "0x" + 64 hex chars
        int(result, 16)

    def test_stable_across_dict_str_path(self, tmp_path):
        """Identical content via dict, JSON string, or file path produces the same hash."""
        from_dict = descriptor_hash(SAMPLE_DESCRIPTOR)
        from_str = descriptor_hash(json.dumps(SAMPLE_DESCRIPTOR))

        path = tmp_path / "descriptor.json"
        path.write_text(json.dumps(SAMPLE_DESCRIPTOR))
        from_path = descriptor_hash(path)

        assert from_dict == from_str == from_path

    def test_jcs_canonicalizes_key_order(self):
        """RFC 8785 canonicalization makes key order irrelevant."""
        reordered = {
            "display": SAMPLE_DESCRIPTOR["display"],
            "context": SAMPLE_DESCRIPTOR["context"],
        }
        assert descriptor_hash(SAMPLE_DESCRIPTOR) == descriptor_hash(reordered)

    def test_jcs_canonicalizes_whitespace(self):
        """Whitespace differences in JSON input don't change the hash."""
        compact = json.dumps(SAMPLE_DESCRIPTOR, separators=(",", ":"))
        pretty = json.dumps(SAMPLE_DESCRIPTOR, indent=2)
        assert descriptor_hash(compact) == descriptor_hash(pretty)

    def test_different_content_different_hash(self):
        modified = {
            **SAMPLE_DESCRIPTOR,
            "context": {**SAMPLE_DESCRIPTOR["context"], "$id": "Other"},
        }
        assert descriptor_hash(SAMPLE_DESCRIPTOR) != descriptor_hash(modified)

    def test_rejects_unsupported_type(self):
        with pytest.raises(TypeError):
            descriptor_hash(42)

    def test_rejects_malformed_json_string(self):
        with pytest.raises(json.JSONDecodeError):
            descriptor_hash("{not json")
