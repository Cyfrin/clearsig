"""Unit tests for the descriptor hashing module."""

import json
from pathlib import Path

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


def _write(directory: Path, name: str, obj: dict) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))
    return path


class TestIncludesResolution:
    """ERC-8176 requires hashing the fully-resolved descriptor (includes merged)."""

    def test_resolved_hash_covers_included_content(self, tmp_path):
        included = {
            "metadata": {"owner": "Common"},
            "display": {
                "formats": {
                    "deposit(uint256 assets)": {
                        "intent": "Deposit",
                        "fields": [{"path": "assets", "label": "Amount", "format": "raw"}],
                    }
                }
            },
        }
        _write(tmp_path, "common.json", included)
        including = {
            "includes": "common.json",
            "context": {"$id": "Child", "contract": {"deployments": []}},
        }
        path = _write(tmp_path, "child.json", including)

        # The spec-resolved equivalent, written out by hand (no merge logic reused).
        flat = {
            "context": {"$id": "Child", "contract": {"deployments": []}},
            "metadata": {"owner": "Common"},
            "display": included["display"],
        }
        assert descriptor_hash(path) == descriptor_hash(flat)
        assert descriptor_hash(path) != descriptor_hash(path, resolve_includes=False)

    def test_including_file_wins_on_conflict(self, tmp_path):
        _write(tmp_path, "common.json", {"metadata": {"owner": "Common", "ticker": "AAA"}})
        path = _write(
            tmp_path,
            "child.json",
            {"includes": "common.json", "metadata": {"owner": "Child"}},
        )
        expected = {"metadata": {"owner": "Child", "ticker": "AAA"}}
        assert descriptor_hash(path) == descriptor_hash(expected)

    def test_fields_arrays_merge_by_path(self, tmp_path):
        _write(
            tmp_path,
            "common.json",
            {
                "display": {
                    "formats": {
                        "f()": {
                            "fields": [
                                {"path": "a", "label": "A", "format": "raw"},
                                {"path": "b", "label": "B", "format": "raw"},
                            ]
                        }
                    }
                }
            },
        )
        path = _write(
            tmp_path,
            "child.json",
            {
                "includes": "common.json",
                "display": {
                    "formats": {
                        "f()": {
                            "fields": [
                                {"path": "b", "label": "B-child"},
                                {"path": "c", "label": "C", "format": "raw"},
                            ]
                        }
                    }
                },
            },
        )
        # Same-path entries merge (child wins per key), new paths append in order.
        expected = {
            "display": {
                "formats": {
                    "f()": {
                        "fields": [
                            {"path": "a", "label": "A", "format": "raw"},
                            {"path": "b", "label": "B-child", "format": "raw"},
                            {"path": "c", "label": "C", "format": "raw"},
                        ]
                    }
                }
            }
        }
        assert descriptor_hash(path) == descriptor_hash(expected)

    def test_nested_includes_resolve_recursively(self, tmp_path):
        _write(tmp_path, "base.json", {"metadata": {"owner": "Base", "info": {"url": "u"}}})
        _write(tmp_path, "mid.json", {"includes": "base.json", "metadata": {"owner": "Mid"}})
        path = _write(
            tmp_path,
            "top.json",
            {"includes": "mid.json", "context": {"$id": "Top"}},
        )
        expected = {"context": {"$id": "Top"}, "metadata": {"owner": "Mid", "info": {"url": "u"}}}
        assert descriptor_hash(path) == descriptor_hash(expected)

    def test_include_relative_to_included_files_directory(self, tmp_path):
        _write(tmp_path, "ercs/base.json", {"metadata": {"owner": "Base"}})
        _write(tmp_path, "registry/proto/common.json", {"includes": "../../ercs/base.json"})
        path = _write(
            tmp_path,
            "registry/proto/child.json",
            {"includes": "common.json", "context": {"$id": "Child"}},
        )
        expected = {"context": {"$id": "Child"}, "metadata": {"owner": "Base"}}
        assert descriptor_hash(path) == descriptor_hash(expected)

    def test_descriptor_without_includes_is_unchanged(self, tmp_path):
        path = _write(tmp_path, "plain.json", SAMPLE_DESCRIPTOR)
        assert descriptor_hash(path) == descriptor_hash(path, resolve_includes=False)

    def test_circular_includes_raise(self, tmp_path):
        _write(tmp_path, "a.json", {"includes": "b.json"})
        path = _write(tmp_path, "b.json", {"includes": "a.json"})
        with pytest.raises(ValueError, match="circular"):
            descriptor_hash(path)

    def test_self_include_raises(self, tmp_path):
        path = _write(tmp_path, "a.json", {"includes": "a.json"})
        with pytest.raises(ValueError, match="circular"):
            descriptor_hash(path)

    def test_missing_included_file_raises(self, tmp_path):
        path = _write(tmp_path, "child.json", {"includes": "nope.json"})
        with pytest.raises(OSError):
            descriptor_hash(path)

    def test_non_string_includes_raises(self, tmp_path):
        path = _write(tmp_path, "child.json", {"includes": ["a.json"]})
        with pytest.raises(ValueError, match="string path"):
            descriptor_hash(path)

    def test_dict_input_with_includes_needs_location(self):
        with pytest.raises(ValueError, match="no file location"):
            descriptor_hash({"includes": "common.json"})
        # Explicitly opting out of resolution still works on bare dicts.
        assert len(descriptor_hash({"includes": "common.json"}, resolve_includes=False)) == 32


FIXTURES = Path(__file__).parent.parent / "fixtures" / "includes"


class TestRegistryVectors:
    """Pinned vectors from real ethereum/clear-signing-erc7730-registry files.

    The 1inch expected hash was computed by two independent implementations
    (Cyfrin/clearsig#16 and this repo's review tooling) — it is the value a
    spec-correct ERC-8176 verifier must reproduce.
    """

    ONEINCH = FIXTURES / "registry" / "1inch" / "calldata-AggregationRouterV4.json"
    KILN = FIXTURES / "registry" / "kiln" / "calldata-Vault-USDC-AAVE-Arbitrum.json"

    def test_1inch_resolved_hash(self):
        assert (
            descriptor_hash_hex(self.ONEINCH)
            == "0x0039d2ccc41196701d4fd730dfa2ffaac85d99ba57e03b8fdd443a63a7d923fc"
        )

    def test_1inch_raw_hash_matches_legacy_behavior(self):
        assert (
            descriptor_hash_hex(self.ONEINCH, resolve_includes=False)
            == "0xd55e8bf5140bb9635522cf3d1a142e4dacf7c05d902fc5ae3d4358f82b57c4cc"
        )

    def test_kiln_nested_include_chain_resolves(self):
        from clearsig import resolve_includes

        descriptor = json.loads(self.KILN.read_text())
        resolved = resolve_includes(descriptor, self.KILN.parent)

        assert "includes" not in json.dumps(resolved)
        # Content from the innermost include (ercs/calldata-erc4626-vaults.json)
        # must be present in the resolved descriptor.
        formats = resolved["display"]["formats"]
        assert any(key.startswith("deposit(") for key in formats)
        # The outermost file's own context survives the merge.
        assert resolved["context"]["contract"]["deployments"]
        assert descriptor_hash(self.KILN) != descriptor_hash(self.KILN, resolve_includes=False)
