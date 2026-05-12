# clearsig

A toolbox for transaction intent verification — so the bytes you sign on a hardware wallet are the bytes you meant to sign.

Implements:

| Standard                                                                                        | What for                                                                                                                        |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| [ERC-7730](https://github.com/ethereum/clear-signing-erc7730-registry)                          | Translate raw EVM calldata to human-readable output using clear-signing descriptors.                                            |
| [ERC-8176](https://ethereum-magicians.org/t/erc-8176-integrity-verification-for-erc-7730/27911) | Descriptor hash for auditor attestations (keccak256 of RFC 8785 JCS-canonicalized JSON).                                        |
| [ERC-8213](https://erc8213.eth.limo/)                                                           | Reproducible digests (calldata, EIP-712 domain / message / final) wallets can display before signing.                           |
| [EIP-712](https://eips.ethereum.org/EIPS/eip-712)                                               | Typed-data hashing for arbitrary domains.                                                                                       |
| [Safe Wallet Hashes](https://github.com/Cyfrin/safe-hash-rs)                                    | Safe transaction / off-chain message / nested-Safe approval hashes — feature parity with `safe-hash-rs` for offline operations. |

> Most of this was written by AI. Please use devcontainers and other methods to isolate your environment when contributing.

## Why

You're about to sign a transaction. Your hardware wallet shows you a hex string. How do you know what you're signing?

- **ERC-7730** answers "what does this calldata mean?" by pairing a function selector with a human-readable descriptor.
- **ERC-8176** lets a third-party auditor sign that a descriptor is correct for a contract, so you can trust descriptors you didn't write yourself.
- **ERC-8213** lets a wallet display short, reproducible cryptographic fingerprints of what you're about to sign, so you can independently compute the same fingerprint on a separate device and compare.
- **Safe hashes** let an owner of a Safe{Wallet} multisig compute — offline, on an isolated machine — what their hardware wallet should show when asked to sign a multisig transaction or message.

`clearsig` rolls all of these into one CLI and Python library.

## Install

`clearsig` is on PyPI. Pick whichever installer you have:

```bash
# uv (recommended — installs into an isolated environment)
uv tool install clearsig

# pipx (alternative — same isolated-tool model)
pipx install clearsig

# pip (installs into your current Python environment)
pip install clearsig
```

For development from source:

```bash
git clone https://github.com/Cyfrin/clearsig.git
cd clearsig
uv sync
uv run clearsig --help
```

The first time you `clearsig translate`, the tool auto-downloads the ERC-7730 registry from `ethereum/clear-signing-erc7730-registry` into `~/.clearsig/registry`. To pre-fetch or refresh:

```bash
clearsig update
```

Or point at a registry checkout you already have:

```bash
export ERC7730_REGISTRY_PATH=/path/to/clear-signing-erc7730-registry
```

## Quick start

```bash
# What does this calldata mean? (ERC-7730 translation)
clearsig translate \
  0xa9059cbb00000000000000000000000092d0ebaf7eb707f0650f9471e61348f4656c29bc00000000000000000000000000000000000000000000000000000005d21dba00 \
  --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --chain-id 1
# Intent: Send
# Function: transfer(address,uint256)
#   Amount: 25000000000
#   To: 0x92d0ebaf7eb707f0650f9471e61348f4656c29bc

# What digest will my hardware wallet display before signing? (ERC-8213)
clearsig calldata-digest 0xa9059cbb0000000000000000000000004675c7e5baafbffbca748158becba61ef3b0a2630000000000000000000000000000000000000000000000000de0b6b3a7640000
# 0x812cee5d9cc7461c04bbcd7b70af9c28b243ac5d74d3453b008b93b7dac69985

# I'm about to sign a Safe transaction — what's the Safe Tx Hash?
clearsig safe-hash \
  --chain-id 1 --safe-address 0x1c694Fc3006D81ff4a56F97E1b99529066a23725 \
  --safe-version 1.4.1 --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 \
  --data 0xa9059cbb00000000000000000000000092d0ebaf7eb707f0650f9471e61348f4656c29bc00000000000000000000000000000000000000000000000000000005d21dba00 \
  --nonce 63
# Safe Transaction Hash (EIP-712 Digest):   0xad06b099fca34e51e4886643d95d9a19ace2cd024065efb66662a876e8c40343

# I'm writing a descriptor for a new contract — give me a starting point
clearsig generate --chain-id 1 --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --owner USDC
```

Run `clearsig --help` or `clearsig <subcommand> --help` for the full surface.

## Commands

### `translate` — read calldata with ERC-7730

Convert raw EVM calldata into human-readable fields using the [ERC-7730 registry](https://github.com/ethereum/clear-signing-erc7730-registry).

```bash
clearsig translate \
  0xa9059cbb00000000000000000000000092d0ebaf7eb707f0650f9471e61348f4656c29bc00000000000000000000000000000000000000000000000000000005d21dba00 \
  --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 \
  --chain-id 1
```
```
Intent: Send
Function: transfer(address,uint256)

  Amount: 25000000000
  To: 0x92d0ebaf7eb707f0650f9471e61348f4656c29bc
```

Recursively decodes nested standard-ABI calls (e.g., a Safe `execTransaction` wrapping an ERC-20 `approve`). For protocols whose inner encoding isn't standard ABI, see [What ERC-7730 doesn't cover](#what-erc-7730-doesnt-cover).

### `descriptor-hash` / `dh` — hash an ERC-7730 descriptor (ERC-8176)

```bash
clearsig descriptor-hash ~/.clearsig/registry/ercs/calldata-erc20-tokens.json
# 0x63c35f8e63515f177d0f120954ce13e1979ab0b12659d29cd6069d07f2710abb
```

Output is the keccak256 of the RFC 8785 JCS-canonicalized JSON — stable across formatting, key order, and trailing whitespace. Auditors sign this hash to attest that a descriptor faithfully represents a contract.

### `calldata` / `cd` — ABI-encode a function call

```bash
clearsig calldata "approve(address,uint256)" 0x05C54380408aB9c31157B7563138F798f7826aA0 1
# 0x095ea7b300000000000000000000000005c54380408ab9c31157b7563138f798f7826aa00000000000000000000000000000000000000000000000000000000000000001
```

Encodes a function signature plus its arguments into the standard 4-byte-selector + ABI-encoded-params calldata layout. Supports primitive types (`address`, `bool`, `intN`/`uintN`, `bytes`/`bytesN`, `string`) and JSON-syntax arrays (`[1,2,3]`, `["0x...","0x..."]`).

### `calldata-decode` — decode calldata against a signature

```bash
clearsig calldata-decode "approve(address,uint256)" \
  0x095ea7b300000000000000000000000005c54380408ab9c31157b7563138f798f7826aa00000000000000000000000000000000000000000000000000000000000000001
# 0x05c54380408ab9c31157b7563138f798f7826aa0
# 1
```

Offline counterpart to `calldata`. Verifies the 4-byte selector matches the signature before decoding so a mistyped signature errors instead of silently producing garbage. Add `--json` for structured output.

### `sig` — function selector from signature

```bash
clearsig sig "approve(address,uint256)"
# 0x095ea7b3
```

The 4-byte selector — first 4 bytes of `keccak256(signature)`.

### `keccak` — keccak256 of input

```bash
clearsig keccak "approve(address,uint256)"
# 0x095ea7b334ae44009aa867bfb386f5c3b4b443ac6f0ee573fa91c4608fbadfba

clearsig keccak 0xdeadbeef
# 0xd4fd4e189132273036449fc9e11198c739161b4c0116a9a2dccdfa1c492006f1
```

If the input starts with `0x`, the hex bytes are hashed; otherwise the UTF-8 bytes of the string are hashed. Pass `--string` to force UTF-8 mode even when the input is `0x…`.

### `4byte` — reverse-lookup a selector

```bash
clearsig 4byte 0x095ea7b3
# approve(address,uint256)
# sign_szabo_bytecode(bytes16,uint128)
# …
```

Queries [4byte.directory](https://www.4byte.directory/) for text signatures matching a 4-byte selector. Results are sorted oldest-first (ascending id) — the earliest registered signature is the conventional pick when multiple results exist (later ones may be hash-collision spam). Requires network access; pair with `calldata-decode` to interpret calldata of unknown origin.

### `calldata-digest` / `cdg` — ERC-8213 calldata digest

```bash
# transfer(0x4675c7..., 1e18) — ERC-20 transfer of 1 token
clearsig calldata-digest 0xa9059cbb0000000000000000000000004675c7e5baafbffbca748158becba61ef3b0a2630000000000000000000000000000000000000000000000000de0b6b3a7640000
# 0x812cee5d9cc7461c04bbcd7b70af9c28b243ac5d74d3453b008b93b7dac69985

# Plain ETH transfer — empty calldata is valid (length prefix is 32 zero bytes)
clearsig cdg 0x
# 0x290decd9548b62a8d60345a988386fc84ba6bc95484008f6362f93160ef3e563
```

`keccak256(uint256(len(calldata)) || calldata)` — a length-prefixed fingerprint. Chain ID is intentionally not included. Useful for cross-device verification before signing a plain transaction.

### `eip712` — EIP-712 typed-data hashes

Sample [examples/eip712_mail.json](examples/eip712_mail.json) is the canonical EIP-712 spec Mail example.

```bash
clearsig eip712 examples/eip712_mail.json
```
```
Domain Hash:  0xf2cee375fa42b42143804025fc449deafd50cc031ca257e0b194a650a912090f
Message Hash: 0xc52c0ee5d84264471806290a3f2c4cecfc5490626bf912d01f240d7a274b371e
Digest:       0xbe609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2
```

Outputs the three EIP-712 hashes specified by ERC-8213:

- **Domain Hash** = `hashStruct(EIP712Domain)`
- **Message Hash** = `hashStruct(primaryType)`
- **Digest** = `keccak256(0x1901 || domainHash || messageHash)`

Add `--json` for machine-readable output.

### `safe-hash` / `sh` — Safe transaction hashes (offline)

A Safe owner about to sign a USDC transfer of 25,000 USDC out of mainnet Safe `0x1c69...3725`, nonce 63:

```bash
clearsig safe-hash \
  --chain-id 1 \
  --safe-address 0x1c694Fc3006D81ff4a56F97E1b99529066a23725 \
  --safe-version 1.4.1 \
  --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 \
  --data 0xa9059cbb00000000000000000000000092d0ebaf7eb707f0650f9471e61348f4656c29bc00000000000000000000000000000000000000000000000000000005d21dba00 \
  --nonce 63
```
```
Domain Hash:                              0x1655e94a9bcc5a957daa1acae692b4c22e7aaf146b4deb9194f8221d2f09d8c3
Message Hash:                             0xf22754eba5a2b230714534b4657195268f00dc0031296de4b835d82e7aa1e574
Safe Transaction Hash (EIP-712 Digest):   0xad06b099fca34e51e4886643d95d9a19ace2cd024065efb66662a876e8c40343
```

Computes the three hashes a Safe wallet displays when an owner is asked to sign. Supports Safe versions ≥ 0.1.0 (handles the 1.0.0 and 1.3.0 spec boundaries automatically). Matches [safe-hash-rs](https://github.com/Cyfrin/safe-hash-rs) byte-for-byte.

#### Nested Safes

When an outer Safe owns the inner Safe, the outer Safe approves the inner tx by calling `approveHash(bytes32)`. Pass both flags to get hashes for both transactions:

```bash
clearsig safe-hash \
  --chain-id 11155111 \
  --safe-address 0xbC7977C6694Ae2Ae8Ad96bb1C100a281D928b7DB \
  --safe-version 1.4.1 \
  --to 0xdd13E55209Fd76AfE204dBda4007C227904f0a81 \
  --data 0xa9059cbb00000000000000000000000036bffa3048d89fad48509c83fdb6a3410232f3d300000000000000000000000000000000000000000000000000038d7ea4c68000 \
  --nonce 0 \
  --nested-safe-address 0x5031f5E2ed384978dca63306dc28A68a6Fc33e81 \
  --nested-safe-nonce 1
```
```
Inner transaction
  Domain Hash:                              0x90318ce95110d65a9b34b62af48c7ea93cd63d2284c84653a8425aa2454b2bd5
  Message Hash:                             0x05f69b6d363fa6efda5a0fce2ce45ff0b73fe3d11cc87d97209fad7b9a2c9020
  Safe Transaction Hash (EIP-712 Digest):   0x2aa2feb008064ccb8d6a31c43a6812d288107501505a04095ecdb2ebbeeaaffc

Outer transaction (approveHash on the inner Safe)
  Approve calldata:                         0xd4d9bdcd2aa2feb008064ccb8d6a31c43a6812d288107501505a04095ecdb2ebbeeaaffc
  Domain Hash:                              0xf0276c332cd121de246e945fa8624ceeb62c7bb0d2ba58900263bef583f974df
  Message Hash:                             0x94942ad850af66fe8e16487406110f8037950e63f79f9baab1f48b9c15d4b291
  Safe Transaction Hash (EIP-712 Digest):   0x2c7a5de4d1bc03ca44ce122ff5feaa4241946737b42ee834a2881fcbe73bfbd6
```

### `safe-msg` / `sm` — Safe off-chain message hashes

For signing plain-text messages with a Safe (e.g., OpenSea sign-in). Computes the EIP-191 hash of the plaintext (line endings normalized to LF), then wraps it in `SafeMessage(bytes message)` and EIP-712 hashes against the Safe's domain.

Sample [examples/opensea_signin.txt](examples/opensea_signin.txt) is the real OpenSea sign-in payload used in `safe-hash-rs`'s reference vector.

```bash
clearsig safe-msg \
  --chain-id 11155111 \
  --safe-address 0x657ff0D4eC65D82b2bC1247b0a558bcd2f80A0f1 \
  --safe-version 1.3.0 \
  --message-file examples/opensea_signin.txt
```
```
Raw Message Hash:                   0xcb1a9208c1a7c191185938c7d304ed01db68677eea4e689d688469aa72e34236
Domain Hash:                        0x611379c19940caee095cdb12bebe6a9fa9abb74cdb1fbd7377c49a1f198dc24f
Message Hash:                       0xa5d2f507a16279357446768db4bd47a03bca0b6acac4632a4c2c96af20d6f6e5
Safe Message Hash (EIP-712 Digest): 0x1866b559f56261ada63528391b93a1fe8e2e33baf7cace94fc6b42202d16ea08
```

Pass `--message "hello"` for inline input instead of `--message-file`.

### `generate` — bootstrap an ERC-7730 descriptor

```bash
clearsig generate \
  --chain-id 1 \
  --to 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 \
  --owner USDC \
  --output usdc.json
# 0xa0b8...eb48 is a ZeppelinOSProxy; following to 0x4350...02dd
```

The proxy traversal is logged to stderr. The descriptor (a couple hundred lines for USDC's 39 functions) lands in `usdc.json`. A representative snippet of the generated output:

```json
{
  "$schema": "https://github.com/ethereum/clear-signing-erc7730-registry/blob/master/specs/erc7730-v1.schema.json",
  "context": {
    "contract": {
      "deployments": [{"chainId": 1, "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}],
      "abi": [ /* 39 function entries from the FiatTokenV2_2 implementation */ ]
    }
  },
  "metadata": {"owner": "USDC"},
  "display": {
    "formats": {
      "transfer(address,uint256)": {
        "fields": [
          {"path": "to", "label": "To", "format": "addressName", "params": {"types": ["eoa", "wallet"]}},
          {"path": "value", "label": "Value", "format": "amount"}
        ]
      },
      "approve(address,uint256)": {
        "fields": [
          {"path": "spender", "label": "Spender", "format": "addressName", "params": {"types": ["contract"]}},
          {"path": "value", "label": "Value", "format": "amount"}
        ]
      }
    }
  }
}
```

Fetches the verified ABI from [Sourcify](https://docs.sourcify.dev/) (auto-traversing proxies to the implementation via `proxyResolution`) and walks each function's inputs. For each parameter it picks a sensible display format from the name — `amount` → `amount`, `spender` → `addressName{contract}`, `deadline` → `date{timestamp}`, `bytes calldata` → `calldata`, etc.

The result is a starter descriptor — descriptor authors should refine labels and intents by hand.

```bash
# Supply an ABI directly if Sourcify doesn't have it
clearsig generate \
  --chain-id 1 \
  --to 0x1234567890123456789012345678901234567890 \
  --abi path/to/abi.json \
  --owner "My Protocol"
```

Notes:
- For multi-implementation proxies (Diamonds), function ABIs are unioned by selector.
- Defaults to ERC-7730 v1 (matches the existing registry). Pass `--v2` to emit v2.
- Override the Sourcify base URL with `--sourcify-url` for self-hosted instances.

## What ERC-7730 doesn't cover

ERC-7730 describes contracts whose `calldata` follows the standard 4-byte-selector + ABI-encoded-params layout. Some real-world contracts diverge from that, and `clearsig translate` can't fully decode them. ERC-8213 digests (the `calldata-digest`, `eip712`, `safe-hash`, and `safe-msg` commands) are the answer for those cases — they let signers verify what's about to be signed even when descriptor-level translation isn't possible.

| Scenario                              | Status | Why                                          |
| ------------------------------------- | ------ | -------------------------------------------- |
| ERC-20 transfer/approve               | ✅      | Generic descriptor, works on any token       |
| Aave v3 supply/borrow/repay           | ✅      | Mainnet, zkSync, Polygon, and more           |
| Safe `execTransaction` → single call  | ✅      | Inner calldata recursively decoded           |
| Safe `execTransaction` → Aave supply  | ✅      | Nested: Safe layer + Aave layer both decoded |
| zkSync `requestL2Transaction` (L1→L2) | ❌      | Missing descriptor from registry             |
| Safe `execTransaction` → MultiSend    | ❌      | Custom packed encoding                       |
| zkSync `sendToL1` (L2→L1 governance)  | ❌      | Custom packed encoding                       |
| Uniswap Universal Router `execute`    | ❌      | Custom packed encoding                       |

Two failure modes account for the ❌ rows:

1. **Missing descriptor** — encoding is standard ABI but no one has written a descriptor yet (e.g., zkSync `requestL2Transaction`). Fixable by adding a descriptor to the registry (`clearsig generate` is a good starting point).
2. **Custom packed encoding** — protocol-specific binary format that doesn't map to ABI types at all (e.g., MultiSend, Uniswap Universal Router). The ERC-7730 schema can't describe these. Use `clearsig calldata-digest` or `clearsig safe-hash` to at least verify *which* bytes are being signed.

[Worked examples](#cli-examples) below show what each case looks like in practice.

## Python SDK

Everything the CLI does is also available as a library.

```python
from clearsig import translate, update_registry

update_registry()  # one-time, saves to ~/.clearsig/registry

result = translate(
    "0x617ba037000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "000000000000000000000000000000000000000000000000000000000000dead"
    "0000000000000000000000000000000000000000000000000000000000000000",
    to="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    chain_id=1,
)

print(result.intent)   # "Supply"
print(result.entity)   # "Aave"
for field in result.fields:
    print(f"  {field.label}: {field.value}")
```

Reuse a loaded registry when translating many inputs:

```python
from clearsig import Registry, translate_with_registry

registry = Registry.load()  # uses env var or ~/.clearsig/registry
result = translate_with_registry(registry, calldata, to="0x...", chain_id=1)
```

Hashes are exposed too:

```python
from clearsig import descriptor_hash_hex
from clearsig._calldata_digest import calldata_digest_hex
from clearsig._eip712 import hash_typed_data
from clearsig._safe_hash import SafeTx, safe_hashes, safe_message_hashes

print(descriptor_hash_hex(Path("registry/lido/calldata-stETH.json")))
print(calldata_digest_hex("0xa9059cbb..."))
print("0x" + hash_typed_data(typed_data_dict).hex())

tx = SafeTx(to="0xA0b8...", value=0, data="0xa9059cbb...", nonce=42)
hashes = safe_hashes(chain_id=1, safe_address="0x1c69...", safe_version="1.4.1", tx=tx)
print("0x" + hashes.safe_tx_hash.hex())
```

## Cross-implementation parity

The hashing code is cross-checked byte-for-byte against the canonical reference implementations:

- **EIP-712 + ERC-8213 calldata digest** ↔ [viem](https://viem.sh/) (regenerable fixtures in `tests/fixtures/parity_vectors.json` covering nested structs, dynamic/fixed arrays, multi-dim arrays, JSON-encoded uint256, mixed atomic types).
- **Safe transaction / message / nested-Safe** ↔ [safe-hash-rs](https://github.com/Cyfrin/safe-hash-rs) (vectors from `crates/safe-utils/tests/hasher_tests.rs`).

The full test suite — 215+ unit + CLI tests — runs in ~3 seconds:

```bash
uv run pytest -q
# or
just check   # ruff + ruff format + ty + pytest
```

Tests against the ERC-7730 registry require a local clone at `./clear-signing-erc7730-registry/`:

```bash
git clone --depth 1 https://github.com/ethereum/clear-signing-erc7730-registry.git
```

To regenerate the viem parity fixtures (when adding new test vectors):

```bash
cd /path/to/cyfrin/chain-tools && node /path/to/clearsig/tests/fixtures/generate_parity_vectors.mjs
```

## Releasing

Releases are cut from `main` via `just`:

```bash
just release patch        # 0.1.0 → 0.1.1, tag v0.1.1, push, cut release
just release minor        # 0.1.0 → 0.2.0
just release major        # 0.1.0 → 1.0.0
just release-draft patch  # cut as a draft instead
```

Under the hood `scripts/release.sh` bumps `pyproject.toml` via `uv version --bump`, commits, tags, pushes, and calls `gh release create --generate-notes`. Publishing the release fires `.github/workflows/publish.yml`, which builds the sdist + wheel and uploads to PyPI via OIDC Trusted Publishing.

One-time PyPI setup: add a Trusted Publisher under [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/) for workflow `publish.yml`, environment `pypi`, repo `Cyfrin/clearsig`.

## CLI examples

### Safe{Wallet} execTransaction wrapping an ERC-20 approve

The inner `approve(Aave Pool, 1000000)` call is recursively decoded.

[View calldata on Cyfrin](https://tools.cyfrin.io/abi-encoding?data=0x6a761202000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb480000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001c00000000000000000000000000000000000000000000000000000000000000044095ea7b300000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e200000000000000000000000000000000000000000000000000000000000f4240000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000)

```bash
clearsig translate \
0x6a761202000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb480000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001c00000000000000000000000000000000000000000000000000000000000000044095ea7b300000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e200000000000000000000000000000000000000000000000000000000000f4240000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000 \
  --to 0x41675C099F32341bf84BFc5382aF534df5C7461a \
  --from-address 0x9467919138E36f0252886519f34a0f8016dDb3a3
```

```
Intent: sign multisig operation (Safe)
Function: execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)

  Operation type: Call
  From Safe: 0x41675C099F32341bf84BFc5382aF534df5C7461a
  Execution signer: 0x9467919138E36f0252886519f34a0f8016dDb3a3
  Transaction: Approve
  -> approve(address,uint256)
  Spender: 0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2
  Amount: 1000000
  Gas amount: 0
  Gas price: 0
  Gas receiver: 0x0000000000000000000000000000000000000000
```

### Safe{Wallet} execTransaction wrapping an Aave v3 supply

The inner `supply(USDC, 1000000, recipient, 0)` call is recursively decoded.

[View calldata on Cyfrin](https://tools.cyfrin.io/abi-encoding?data=0x6a76120200000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000084617ba037000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb4800000000000000000000000000000000000000000000000000000000000f42400000000000000000000000009467919138e36f0252886519f34a0f8016ddb3a30000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000)

```bash
clearsig translate \
  0x6a76120200000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e20000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000084617ba037000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb4800000000000000000000000000000000000000000000000000000000000f42400000000000000000000000009467919138e36f0252886519f34a0f8016ddb3a30000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000 \
  --to 0x41675C099F32341bf84BFc5382aF534df5C7461a \
  --from-address 0x9467919138E36f0252886519f34a0f8016dDb3a3
```

```
Intent: sign multisig operation (Safe)
Function: execTransaction(address,uint256,bytes,uint8,uint256,uint256,uint256,address,address,bytes)

  Operation type: Call
  From Safe: 0x41675C099F32341bf84BFc5382aF534df5C7461a
  Execution signer: 0x9467919138E36f0252886519f34a0f8016dDb3a3
  Transaction: Supply (Aave)
  -> supply(address,uint256,address,uint16)
  Amount to supply: 1000000
  Collateral recipient: 0x9467919138e36f0252886519f34a0f8016ddb3a3
  Gas amount: 0
  Gas price: 0
  Gas receiver: 0x0000000000000000000000000000000000000000
```

### Safe{Wallet} execTransaction via MultiSend (hits schema limits)

A delegate call to MultiSend batching an ERC-20 approve + Aave supply. The outer Safe layer decodes, but the MultiSend packed encoding is not standard ABI, so the inner transactions show as raw hex.

```bash
clearsig translate \
  0x6a76120200000000000000000000000038869bf66a61cf6bdb996a6ae40d5853fd43b526... \
  --to 0x41675C099F32341bf84BFc5382aF534df5C7461a \
  --from-address 0x9467919138E36f0252886519f34a0f8016dDb3a3
```

The `Transaction` field comes back as raw hex because MultiSend uses a custom packed encoding (not standard ABI). When you hit this case, fall back to `clearsig calldata-digest` on the inner bytes (or `clearsig safe-hash` on the outer Safe tx) — at least the fingerprint matches what your hardware wallet will show.

### zkSync Era `requestL2Transaction` (no descriptor)

An L1→L2 message via the zkSync Era Mailbox calling `grantRole` on an L2 contract.

```bash
clearsig translate 0xeb672419... --to 0x32400084C286CF3E17e7B677ea9583e60a000324 --chain-id 1
# Error: No ERC-7730 descriptor found for selector 0xeb672419 on 0x32400084C286CF3E17e7B677ea9583e60a000324 (chain 1)
```

Fix: write a descriptor and submit it to the registry (`clearsig generate` produces a starting point).

### Uniswap Universal Router (no descriptor)

The Universal Router's `execute(bytes,bytes[],uint256)` uses a custom command encoding not in the ERC-7730 registry.

```bash
clearsig translate 0x3593564c... --to 0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD --chain-id 1
# Error: No ERC-7730 descriptor found for selector 0x3593564c on 0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD (chain 1)
```

Same fix: write a descriptor. Even with one, the inner command encoding can't be expressed in ERC-7730 — verify the calldata digest instead.

### zkSync `sendToL1` L2→L1 governance call (implicit selector)

An L2→L1 message via the zkSync L1Messenger system contract (`0x...8008`). The inner bytes are an ABI-encoded `UpgradeProposal` struct — but **without a function selector**. ERC-7730 expects a selector to drive lookup, so this can't currently be decoded by translation. Use `clearsig calldata-digest` for at-the-byte-level verification.
