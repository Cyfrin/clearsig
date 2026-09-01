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

    def test_null_includes_rejected(self, tmp_path):
        """Explicit JSON null is not a valid include reference, not an absent key."""
        path = tmp_path / "child.json"
        path.write_text('{"includes": null, "context": {"$id": "X"}}')
        with pytest.raises(ValueError, match="non-empty string"):
            descriptor_hash(path)

    def test_empty_includes_rejected(self, tmp_path):
        path = _write(tmp_path, "child.json", {"includes": ""})
        with pytest.raises(ValueError, match="non-empty string"):
            descriptor_hash(path)

    @pytest.mark.parametrize(
        "uri",
        [
            "https://example.com/common.json",
            "https:example.com/common.json",
            "http:/example.com/common.json",
            "file:/tmp/common.json",
            "urn:example:common",
        ],
    )
    def test_uri_includes_rejected(self, tmp_path, uri):
        """ERC-7730 allows URL includes; clearsig supports local paths only and says so.

        Any RFC 3986 scheme form must hit the explicit rejection, not fall
        through to a confusing FileNotFoundError.
        """
        path = _write(tmp_path, "child.json", {"includes": uri})
        with pytest.raises(ValueError, match="URI includes are not supported"):
            descriptor_hash(path)

    def test_included_non_object_json_rejected(self, tmp_path):
        (tmp_path / "common.json").write_text("[1, 2, 3]")
        path = _write(tmp_path, "child.json", {"includes": "common.json"})
        with pytest.raises(ValueError, match="JSON object"):
            descriptor_hash(path)

    def test_non_object_root_rejected(self):
        """ERC-8176 defines the hash over a descriptor object, not arbitrary JSON."""
        with pytest.raises(ValueError, match="JSON object"):
            descriptor_hash("[1, 2, 3]")

    def test_depth_limit_enforced(self, tmp_path):
        for i in range(34):
            _write(tmp_path, f"d{i}.json", {"includes": f"d{i + 1}.json"})
        _write(tmp_path, "d34.json", {"metadata": {"owner": "Leaf"}})
        with pytest.raises(ValueError, match="depth limit"):
            descriptor_hash(tmp_path / "d0.json")

    def test_duplicate_paths_in_included_rejected(self, tmp_path):
        _write(
            tmp_path,
            "common.json",
            {"display": {"formats": {"f()": {"fields": [{"path": "a"}, {"path": "a"}]}}}},
        )
        path = _write(
            tmp_path,
            "child.json",
            {"includes": "common.json", "display": {"formats": {"f()": {"fields": []}}}},
        )
        with pytest.raises(ValueError, match="duplicate fields path"):
            descriptor_hash(path)

    def test_duplicate_paths_in_including_rejected(self, tmp_path):
        _write(
            tmp_path,
            "common.json",
            {"display": {"formats": {"f()": {"fields": [{"path": "a"}]}}}},
        )
        path = _write(
            tmp_path,
            "child.json",
            {
                "includes": "common.json",
                "display": {"formats": {"f()": {"fields": [{"path": "b"}, {"path": "b"}]}}},
            },
        )
        with pytest.raises(ValueError, match="duplicate fields path"):
            descriptor_hash(path)

    def test_duplicates_outside_a_merge_are_left_as_written(self, tmp_path):
        """Duplicate paths are rejected only where two fields arrays actually
        merge; a format that never participates in a merge has no ambiguity
        and is hashed as written."""
        descriptor = {"display": {"formats": {"f()": {"fields": [{"path": "a"}, {"path": "a"}]}}}}
        path = _write(tmp_path, "root.json", descriptor)
        assert descriptor_hash(path) == descriptor_hash(descriptor)

    def test_input_object_is_not_mutated(self, tmp_path):
        _write(tmp_path, "common.json", {"metadata": {"owner": "Common"}})
        descriptor = {"includes": "common.json", "context": {"$id": "Child"}}
        snapshot = json.dumps(descriptor, sort_keys=True)
        from clearsig import resolve_includes

        resolve_includes(descriptor, tmp_path)
        assert json.dumps(descriptor, sort_keys=True) == snapshot


class TestIncludeRootContainment:
    """Resolved includes must stay inside a trusted root (v0.3.1 guard, extended)."""

    def test_traversal_escape_blocked(self, tmp_path):
        """A descriptor under registry/ cannot read files outside the checkout root."""
        _write(tmp_path, "outside.json", {"metadata": {"owner": "ESCAPED"}})
        checkout = tmp_path / "checkout"
        path = _write(checkout, "registry/proto/evil.json", {"includes": "../../../outside.json"})
        with pytest.raises(ValueError, match="escapes the include root"):
            descriptor_hash(path)

    def test_absolute_style_escape_blocked(self, tmp_path):
        _write(tmp_path, "secret.json", {"metadata": {"owner": "SECRET"}})
        path = _write(
            tmp_path,
            "checkout/registry/proto/evil.json",
            {"includes": str(tmp_path / "secret.json")},
        )
        with pytest.raises(ValueError, match="escapes the include root"):
            descriptor_hash(path)

    def test_symlink_escape_blocked(self, tmp_path):
        _write(tmp_path, "outside/secret.json", {"metadata": {"owner": "SECRET"}})
        checkout = tmp_path / "checkout"
        path = _write(checkout, "registry/proto/child.json", {"includes": "link.json"})
        (checkout / "registry" / "proto" / "link.json").symlink_to(
            tmp_path / "outside" / "secret.json"
        )
        with pytest.raises(ValueError, match="escapes the include root"):
            descriptor_hash(path)

    def test_default_root_confines_standalone_descriptor_to_its_directory(self, tmp_path):
        _write(tmp_path, "shared.json", {"metadata": {"owner": "Shared"}})
        path = _write(tmp_path, "sub/child.json", {"includes": "../shared.json"})
        with pytest.raises(ValueError, match="escapes the include root"):
            descriptor_hash(path)

    def test_explicit_wider_root_allows_the_include(self, tmp_path):
        _write(tmp_path, "shared.json", {"metadata": {"owner": "Shared"}})
        path = _write(tmp_path, "sub/child.json", {"includes": "../shared.json"})
        expected = {"metadata": {"owner": "Shared"}}
        assert descriptor_hash(path, include_root=tmp_path) == descriptor_hash(expected)

    def test_registry_layout_cross_tree_include_allowed_by_default(self, tmp_path):
        """The real registry shape (registry/<p>/ -> ../../ercs/) needs no flags."""
        _write(tmp_path, "checkout/ercs/base.json", {"metadata": {"owner": "Base"}})
        path = _write(
            tmp_path,
            "checkout/registry/proto/child.json",
            {"includes": "../../ercs/base.json", "context": {"$id": "Child"}},
        )
        expected = {"context": {"$id": "Child"}, "metadata": {"owner": "Base"}}
        assert descriptor_hash(path) == descriptor_hash(expected)

    def test_symlinked_descriptor_blocked(self, tmp_path):
        """Root inference is lexical: a symlinked descriptor must not relocate
        the trusted root to wherever its target lives."""
        outside = tmp_path / "outside"
        _write(outside, "secret.json", {"metadata": {"owner": "SECRET"}})
        _write(outside, "child.json", {"includes": "secret.json"})
        checkout = tmp_path / "checkout"
        (checkout / "registry" / "proto").mkdir(parents=True)
        (checkout / "ercs").mkdir()
        link = checkout / "registry" / "proto" / "child.json"
        link.symlink_to(outside / "child.json")
        with pytest.raises(ValueError, match="outside the include root"):
            descriptor_hash(link)

    def test_symlinked_protocol_directory_blocked(self, tmp_path):
        outside = tmp_path / "outside"
        _write(outside, "secret.json", {"metadata": {"owner": "SECRET"}})
        _write(outside, "child.json", {"includes": "secret.json"})
        checkout = tmp_path / "checkout"
        (checkout / "registry").mkdir(parents=True)
        (checkout / "ercs").mkdir()
        (checkout / "registry" / "proto").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="outside the include root"):
            descriptor_hash(checkout / "registry" / "proto" / "child.json")

    def test_symlinked_plain_descriptor_blocked(self, tmp_path):
        """Containment applies to every Path descriptor, with or without
        `includes` — a symlinked plain descriptor must not hash either."""
        outside = tmp_path / "outside"
        _write(outside, "plain.json", {"metadata": {"owner": "SECRET"}})
        checkout = tmp_path / "checkout"
        (checkout / "registry" / "proto").mkdir(parents=True)
        (checkout / "ercs").mkdir()
        link = checkout / "registry" / "proto" / "plain.json"
        link.symlink_to(outside / "plain.json")
        with pytest.raises(ValueError, match="outside the include root"):
            descriptor_hash(link)
        # Legacy raw mode deliberately follows the path as given.
        assert len(descriptor_hash(link, resolve_includes=False)) == 32

    def test_containment_checked_before_the_file_is_read(self, tmp_path):
        """An out-of-root descriptor is rejected for containment before its
        bytes are ever parsed — invalid JSON outside the root must raise the
        containment ValueError, not JSONDecodeError."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "bad.json").write_text("{not json")
        checkout = tmp_path / "checkout"
        (checkout / "registry" / "proto").mkdir(parents=True)
        (checkout / "ercs").mkdir()
        link = checkout / "registry" / "proto" / "bad.json"
        link.symlink_to(outside / "bad.json")
        with pytest.raises(ValueError, match="outside the include root"):
            descriptor_hash(link)

    def test_include_root_applies_to_descriptor_without_includes(self, tmp_path):
        """An explicit include_root confines plain descriptors too."""
        outside = tmp_path / "outside"
        target = _write(outside, "plain.json", {"metadata": {"owner": "X"}})
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        link = elsewhere / "plain.json"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="outside the include root"):
            descriptor_hash(link, include_root=elsewhere)
        # A root that does contain the resolved target allows it.
        assert descriptor_hash(link, include_root=tmp_path) == descriptor_hash(target)

    def test_symlinked_layout_marker_does_not_widen_root(self, tmp_path):
        """A symlinked registry/ or ercs/ marker must not satisfy the
        recognized-layout test — the fallback confinement stays at the
        descriptor's own directory."""
        (tmp_path / "elsewhere").mkdir()
        checkout = tmp_path / "checkout"
        _write(checkout, "target.json", {"metadata": {"owner": "AT-CHECKOUT-ROOT"}})
        path = _write(checkout, "registry/proto/child.json", {"includes": "../../target.json"})
        (checkout / "ercs").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        # With a real ercs/ the layout would be recognized and this include
        # (a file at the checkout root) would be allowed; the symlinked
        # marker must instead leave the root at the descriptor's directory.
        with pytest.raises(ValueError, match="escapes the include root"):
            descriptor_hash(path)


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

    def test_kiln_resolved_hash(self):
        """Nested-chain pinned vector, independently confirmed by two resolvers."""
        assert (
            descriptor_hash_hex(self.KILN)
            == "0xe2443fecdf4c1cd44c3ddf5bdeb754837f222ea0c75d44f5209bab244eed441b"
        )

    def test_included_file_only_edit_changes_hash(self, tmp_path):
        """Editing ONLY the included file must change the descriptor's hash.

        This is the 'included file substitution' threat ERC-8176 resolution
        exists to close: the descriptor file itself is byte-identical in both
        trees, but its effective content differs.
        """
        import shutil

        for tree in ("a", "b"):
            dest = tmp_path / tree / "registry" / "1inch"
            dest.parent.mkdir(parents=True)
            shutil.copytree(self.ONEINCH.parent, dest)
        edited = tmp_path / "b" / "registry" / "1inch" / "common-AggregationRouterV4.json"
        common = json.loads(edited.read_text())
        common["metadata"]["owner"] = "TAMPERED"
        edited.write_text(json.dumps(common))

        original = tmp_path / "a" / "registry" / "1inch" / self.ONEINCH.name
        tampered = tmp_path / "b" / "registry" / "1inch" / self.ONEINCH.name
        assert original.read_bytes() == tampered.read_bytes()  # descriptor file identical
        assert descriptor_hash(original) != descriptor_hash(tampered)
        assert descriptor_hash(original, resolve_includes=False) == descriptor_hash(
            tampered, resolve_includes=False
        )  # the legacy hash is blind to exactly this
