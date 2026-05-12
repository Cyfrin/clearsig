# Changelog

All notable changes to `clearsig` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`calldata`** (alias `cd`) — ABI-encode a function signature and arguments into
  calldata. Example: `clearsig calldata "approve(address,uint256)" 0x05C5...aA0 1`.
  Supports primitive types and JSON-syntax arrays.
- **`calldata-decode`** — offline inverse of `calldata`. Decodes ABI-encoded
  calldata against a signature and verifies the selector matches.
- **`sig`** — compute the 4-byte function selector from a signature.
  Example: `clearsig sig "approve(address,uint256)"` → `0x095ea7b3`.
- **`keccak`** — keccak256 of hex bytes (`0x…`) or UTF-8 string. `--string`
  forces UTF-8 mode.
- **`4byte`** — reverse-lookup a 4-byte selector via [4byte.directory](https://www.4byte.directory/).
  Results sorted oldest-first (ascending id) so the canonical signature comes
  before collision spam.
- Python SDK: `encode_calldata`, `encode_calldata_hex`,
  `decode_calldata_with_signature`, `lookup_selector` (in `clearsig._fourbyte`).

### Changed

- **Breaking**: `calldata-digest`'s short alias moved from `cd` to `cdg`, so `cd`
  can match the Foundry convention of `cd` = `calldata` encoding.

## [0.2.0] - 2026-05-11

### Added

- **`calldata-digest`** (alias `cd`) — ERC-8213 length-prefixed calldata digest:
  `keccak256(uint256(len) || calldata)`.
- **`eip712`** — domain hash, message hash, and final EIP-712 digest of any typed-data
  document. Cross-checked byte-for-byte against viem on the EIP-712 spec Mail
  example, Permit2, mixed atomic types, dynamic/fixed-size arrays, multi-dim arrays,
  and arrays of struct.
- **`safe-hash`** (alias `sh`) — Safe transaction hashes (offline) matching
  `safe-hash-rs` byte-for-byte. Supports Safe versions ≥ 0.1.0; handles the
  1.0.0 (`baseGas` vs `dataGas`) and 1.3.0 (`chainId` in domain) spec boundaries.
- **`safe-hash --nested-safe-address / --nested-safe-nonce`** — when the inner
  Safe is owned by an outer Safe, computes hashes for both the inner tx and the
  outer Safe's `approveHash(bytes32)` transaction.
- **`safe-msg`** (alias `sm`) — SafeMessage hashes for off-chain message signing.
  Plaintext line endings are normalized to LF; EIP-191-hashed before being
  wrapped in `SafeMessage(bytes message)` and EIP-712 hashed.
- **`generate`** — bootstrap a starter ERC-7730 descriptor for a contract by
  fetching its verified ABI from [Sourcify](https://docs.sourcify.dev/). Auto-traverses
  proxies (EIP-1967, ZeppelinOS, Diamond, etc.) via `proxyResolution`. Heuristically
  picks display formats from parameter names. Supports v1 (default) and v2 schemas.
- **`examples/`** — `eip712_mail.json` (canonical EIP-712 spec example) and
  `opensea_signin.txt` (real OpenSea sign-in payload), so CLI examples in the
  README are copy-pasteable.
- **Parity test suite** — `tests/unit/test_parity.py` + `tests/fixtures/parity_vectors.json`
  asserts byte-for-byte agreement with viem across 14 vectors. Fixtures regenerable
  via `tests/fixtures/generate_parity_vectors.mjs`.
- **CI workflow** (`.github/workflows/ci.yml`) — runs lint, format check, type
  check, tests, and `pip-audit` on every PR and push to `main`.
- **`prek` pre-commit hooks** (`.pre-commit-config.yaml`) — whitespace / EOF /
  YAML / JSON / merge-conflict / large-file checks plus ruff. Install with
  `just prek-install`.
- **`just audit`** — local supply-chain audit (`uvx pip-audit --strict`).
- **`scripts/update_changelog.py`** — called by `scripts/release.sh` to move
  `[Unreleased]` content under a `[vX.Y.Z]` header with today's date and refresh
  the link references. Refuses to run if `[Unreleased]` is empty.

### Changed

- **Breaking**: renamed `hash` subcommand to `descriptor-hash` (alias `dh`).
  The previous name was ambiguous given the new ERC-8213 digest commands.
- Final Safe-related outputs are now labeled `(EIP-712 Digest)` to match
  ERC-8213 terminology. CLI output columns are aligned with explicit widths.
- Devcontainer `postCreateCommand` now runs `uv sync && uv run clearsig update`
  (was `uv venv && source .venv/bin/activate && uv sync --all-extras`). Drops
  the misleading `--all-extras` and pre-fetches the registry so registry-dependent
  tests pass on container creation.
- README restructured around the broader feature set; the "What ERC-7730 doesn't
  cover" content is now its own section.

### Security

- Added `clearsig/_validate.py` and wired into `safe-hash`, `safe-msg`, and
  `generate` so malformed addresses (`0xnotanaddress`) and hex (`not-hex`)
  surface a clear error instead of an opaque exception from `eth_abi`.

## [0.1.0] - 2026-05-11

### Added

- Initial release on PyPI as `clearsig`.
- **`translate`** — convert raw EVM calldata to human-readable output using
  [ERC-7730](https://github.com/ethereum/clear-signing-erc7730-registry) clear-signing
  descriptors. Recursively decodes nested standard-ABI inner calls (e.g., a Safe
  `execTransaction` wrapping an ERC-20 `approve`).
- **`update`** — download / update the ERC-7730 registry from
  `ethereum/clear-signing-erc7730-registry` into `~/.clearsig/registry`.
- **`hash`** — compute the ERC-8176 descriptor hash (keccak256 of RFC 8785
  JCS-canonicalized JSON) for auditor attestations. *(Renamed to `descriptor-hash`
  in the next release.)*
- **Python SDK**: `translate`, `translate_with_registry`, `update_registry`,
  `Registry`, `descriptor_hash`, `descriptor_hash_hex`.
- **Release infrastructure**: `scripts/release.sh`, `Justfile` (`release`,
  `release-draft`, `check`, etc.), PyPI publish workflow with OIDC Trusted
  Publishing.

[Unreleased]: https://github.com/Cyfrin/clearsig/compare/0.2.0...HEAD
[0.2.0]: https://github.com/Cyfrin/clearsig/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/Cyfrin/clearsig/releases/tag/0.1.0
