# erc7730-converter

Convert raw EVM calldata to human-readable output using [ERC-7730](https://github.com/LedgerHQ/clear-signing-erc7730-registry) clear signing descriptors.

> Most of this was written by AI and has not been thoroughly vetted. Please use devcontainers and other methods to isolate your environment before running.

## Setup

```bash
# Install
uv sync

# Download the ERC-7730 registry (one-time)
uv run erc7730 update
```

Or set a custom registry path:

```bash
export ERC7730_REGISTRY_PATH=/path/to/clear-signing-erc7730-registry
```

## Usage

### Python SDK

```python
from erc7730 import translate, update_registry

# Download registry (one-time, saves to ~/.erc7730/registry)
update_registry()

# Translate calldata
result = translate(
    "0x617ba037000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "000000000000000000000000000000000000000000000000000000000000dead"
    "0000000000000000000000000000000000000000000000000000000000000000",
    to="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    chain_id=1,
)

print(result.intent)  # "Supply"
print(result.entity)  # "Aave"
for field in result.fields:
    print(f"  {field.label}: {field.value}")
```

You can also load the registry once and reuse it:

```python
from erc7730 import Registry, translate_with_registry

registry = Registry.from_path("/path/to/clear-signing-erc7730-registry")
# or
registry = Registry.load()  # uses env var or ~/.erc7730/registry

result = translate_with_registry(registry, calldata, to="0x...", chain_id=1)
```

### CLI

```bash
# ERC-20 approve
erc7730 translate 0x095ea7b3...  --to 0xTokenAddress --chain-id 1

# Aave supply on zkSync Era
erc7730 translate 0x617ba037... --to 0x78e30497a3c7527d953c6B1E3541b021A98Ac43c --chain-id 324

# Safe execTransaction with sender context
erc7730 translate 0x6a761202... \
  --to 0x41675C099F32341bf84BFc5382aF534df5C7461a \
  --from-address 0xYourAddress

# JSON output
erc7730 translate 0x... --to 0x... --json

# Update registry
erc7730 update
```

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only CLI tests
uv run pytest tests/cli/ -v
```

Tests require the local registry at `./clear-signing-erc7730-registry/`. Clone it if you don't have it:

```bash
git clone --depth 1 https://github.com/LedgerHQ/clear-signing-erc7730-registry.git
```

## Supported protocols

Any protocol with descriptors in the [ERC-7730 registry](https://github.com/LedgerHQ/clear-signing-erc7730-registry/tree/master/registry), including:

- ERC-20/721/4626 (generic)
- Aave v3
- Safe{Wallet}
- Uniswap
- Lido
- MakerDAO
- And [40+ more](https://github.com/LedgerHQ/clear-signing-erc7730-registry/tree/master/registry)

# CLI Example

```
uv run erc7730 translate 0x6a761202000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb480000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001c00000000000000000000000000000000000000000000000000000000000000044095ea7b300000000000000000000000087870bca3f3fd6335c3f4ce8392d69350b4fa4e200000000000000000000000000000000000000000000000000000000000f4240000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000 --to 0x41675C099F32341bf84BFc5382aF534df5C7461a --registry-path clear-signing-erc7730-registry --from-address 0x1234567890abcdef1234567890abcdef12345678
```