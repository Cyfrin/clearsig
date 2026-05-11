"""CLI for clearsig calldata translation."""

import argparse
import json
import sys
from pathlib import Path

from clearsig import Registry, descriptor_hash_hex, translate_with_registry, update_registry


def app() -> None:
    """Entry point for the clearsig CLI."""
    parser = argparse.ArgumentParser(
        prog="clearsig",
        description="Translate EVM calldata to human-readable output using ERC-7730 descriptors.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # translate subcommand
    translate_parser = subparsers.add_parser(
        "translate", help="Translate raw calldata to human-readable output"
    )
    translate_parser.add_argument("calldata", help="Hex-encoded calldata (with or without 0x)")
    translate_parser.add_argument("--to", required=True, help="Contract address being called")
    translate_parser.add_argument("--chain-id", type=int, default=1, help="Chain ID (default: 1)")
    translate_parser.add_argument("--registry-path", help="Path to the ERC-7730 registry directory")
    translate_parser.add_argument("--from-address", help="Sender address for display context")
    translate_parser.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # update subcommand
    subparsers.add_parser("update", help="Download or update the ERC-7730 registry")

    # descriptor-hash subcommand (renamed from `hash`)
    descriptor_hash_parser = subparsers.add_parser(
        "descriptor-hash",
        aliases=["dh"],
        help="Compute the ERC-8176 descriptor hash (keccak256 of RFC 8785 JCS-canonicalized JSON)",
    )
    descriptor_hash_parser.add_argument(
        "file",
        type=Path,
        help="Path to the ERC-7730 descriptor JSON file",
    )

    # calldata-digest subcommand
    calldata_digest_parser = subparsers.add_parser(
        "calldata-digest",
        aliases=["cd"],
        help="Compute the ERC-8213 calldata digest: keccak256(uint256(len) || calldata)",
    )
    calldata_digest_parser.add_argument(
        "calldata",
        help="Hex-encoded calldata (with or without 0x). Use '0x' for an empty payload.",
    )

    # eip712 subcommand
    eip712_parser = subparsers.add_parser(
        "eip712",
        help="Compute the three EIP-712 hashes (domain, message, digest) for a typed-data document",
    )
    eip712_parser.add_argument(
        "file",
        type=Path,
        help="Path to a JSON file with `types`, `primaryType`, `domain`, `message`",
    )
    eip712_parser.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # safe-hash subcommand
    safe_hash_parser = subparsers.add_parser(
        "safe-hash",
        aliases=["sh"],
        help="Compute Safe transaction hashes (domain, message, safe tx hash) — offline",
    )
    safe_hash_parser.add_argument("--chain-id", type=int, required=True, help="EIP-155 chain ID")
    safe_hash_parser.add_argument("--safe-address", required=True, help="Safe contract address")
    safe_hash_parser.add_argument(
        "--safe-version", default="1.4.1", help="Safe contract version (default: 1.4.1)"
    )
    safe_hash_parser.add_argument("--to", required=True, help="Transaction `to` address")
    safe_hash_parser.add_argument("--value", type=int, default=0, help="Native value (wei)")
    safe_hash_parser.add_argument(
        "--data", default="0x", help="Inner calldata (hex, with or without 0x)"
    )
    safe_hash_parser.add_argument(
        "--operation", type=int, default=0, help="0 = CALL (default), 1 = DELEGATECALL"
    )
    safe_hash_parser.add_argument("--safe-tx-gas", type=int, default=0)
    safe_hash_parser.add_argument(
        "--base-gas", type=int, default=0, help="`baseGas` (or `dataGas` on Safe < 1.0.0)"
    )
    safe_hash_parser.add_argument("--gas-price", type=int, default=0)
    safe_hash_parser.add_argument(
        "--gas-token", default="0x0000000000000000000000000000000000000000"
    )
    safe_hash_parser.add_argument(
        "--refund-receiver", default="0x0000000000000000000000000000000000000000"
    )
    safe_hash_parser.add_argument("--nonce", type=int, required=True, help="Safe nonce")
    safe_hash_parser.add_argument(
        "--nested-safe-address",
        help="Outer Safe address (when the inner Safe is owned by another Safe)",
    )
    safe_hash_parser.add_argument(
        "--nested-safe-nonce",
        type=int,
        help="Nonce of the outer Safe's approveHash transaction",
    )
    safe_hash_parser.add_argument(
        "--nested-safe-version",
        help="Outer Safe version (defaults to --safe-version)",
    )
    safe_hash_parser.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # safe-msg subcommand
    safe_msg_parser = subparsers.add_parser(
        "safe-msg",
        aliases=["sm"],
        help="Compute Safe off-chain message hashes (SafeMessage typed-data)",
    )
    safe_msg_parser.add_argument("--chain-id", type=int, required=True, help="EIP-155 chain ID")
    safe_msg_parser.add_argument("--safe-address", required=True, help="Safe contract address")
    safe_msg_parser.add_argument(
        "--safe-version", default="1.4.1", help="Safe contract version (default: 1.4.1)"
    )
    msg_source = safe_msg_parser.add_mutually_exclusive_group(required=True)
    msg_source.add_argument("--message", help="Inline plaintext message")
    msg_source.add_argument(
        "--message-file", type=Path, help="Path to a file containing the plaintext message"
    )
    safe_msg_parser.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # generate subcommand
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a starter ERC-7730 descriptor for a contract's ABI",
        description=(
            "Build a minimal ERC-7730 calldata descriptor for a contract. By default the "
            "ABI is fetched from Sourcify and any proxy contract is followed to its "
            "implementation(s). Pass --abi to skip the network call. The output is a "
            "starter — descriptor authors should refine labels and intents by hand."
        ),
    )
    generate_parser.add_argument("--chain-id", type=int, required=True, help="EIP-155 chain ID")
    generate_parser.add_argument("--to", required=True, help="Contract address")
    generate_parser.add_argument(
        "--abi", type=Path, help="Path to a JSON ABI file (skips Sourcify fetch)"
    )
    generate_parser.add_argument("--owner", help="Display name of the owner")
    generate_parser.add_argument("--legal-name", help="Full legal name of the owner")
    generate_parser.add_argument("--url", help="URL with more info on the owner")
    generate_parser.add_argument(
        "--v2", action="store_true", help="Emit ERC-7730 v2 schema (default: v1)"
    )
    generate_parser.add_argument(
        "--sourcify-url",
        default="https://sourcify.dev/server",
        help="Sourcify server base URL",
    )
    generate_parser.add_argument(
        "--output", "-o", type=Path, help="Write output to file (default: stdout)"
    )

    args = parser.parse_args()

    if args.command == "translate":
        _handle_translate(args)
    elif args.command == "update":
        _handle_update()
    elif args.command in ("descriptor-hash", "dh"):
        _handle_descriptor_hash(args)
    elif args.command in ("calldata-digest", "cd"):
        _handle_calldata_digest(args)
    elif args.command == "eip712":
        _handle_eip712(args)
    elif args.command in ("safe-hash", "sh"):
        _handle_safe_hash(args)
    elif args.command in ("safe-msg", "sm"):
        _handle_safe_msg(args)
    elif args.command == "generate":
        _handle_generate(args)


def _handle_translate(args: argparse.Namespace) -> None:
    try:
        registry = Registry.from_path(args.registry_path) if args.registry_path else Registry.load()
        result = translate_with_registry(
            registry,
            args.calldata,
            to=args.to,
            chain_id=args.chain_id,
            from_address=args.from_address,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output_json:
        output = {
            "intent": result.intent,
            "function_name": result.function_name,
            "function_signature": result.function_signature,
            "entity": result.entity,
            "fields": [
                {"label": f.label, "value": f.value, "path": f.path, "format": f.format}
                for f in result.fields
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        _print_human(result)


def _print_human(result) -> None:
    entity_str = f" ({result.entity})" if result.entity else ""
    print(f"Intent: {result.intent}{entity_str}")
    print(f"Function: {result.function_signature}")
    print()
    for field in result.fields:
        print(f"  {field.label}: {field.value}")


def _handle_update() -> None:
    path = update_registry()
    print(f"Registry updated at {path}")


def _handle_descriptor_hash(args: argparse.Namespace) -> None:
    try:
        print(descriptor_hash_hex(args.file))
    except (OSError, json.JSONDecodeError, TypeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_calldata_digest(args: argparse.Namespace) -> None:
    from clearsig._calldata_digest import calldata_digest_hex

    try:
        print(calldata_digest_hex(args.calldata))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_eip712(args: argparse.Namespace) -> None:
    from clearsig._eip712 import hash_domain, hash_message, hash_typed_data

    try:
        doc = json.loads(args.file.read_text())
        for required in ("types", "primaryType", "domain", "message"):
            if required not in doc:
                raise ValueError(f"missing required field: {required}")
        domain = "0x" + hash_domain(doc).hex()
        message = "0x" + hash_message(doc).hex()
        digest = "0x" + hash_typed_data(doc).hex()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output_json:
        payload = {"domainHash": domain, "messageHash": message, "digest": digest}
        print(json.dumps(payload, indent=2))
    else:
        print(f"Domain Hash:  {domain}")
        print(f"Message Hash: {message}")
        print(f"Digest:       {digest}")


def _handle_safe_hash(args: argparse.Namespace) -> None:
    from clearsig._safe_hash import SafeTx, nested_safe_hashes, safe_hashes
    from clearsig._validate import validate_address, validate_hex

    nested = args.nested_safe_address is not None or args.nested_safe_nonce is not None
    if nested and (args.nested_safe_address is None or args.nested_safe_nonce is None):
        print(
            "Error: --nested-safe-address and --nested-safe-nonce must be provided together",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        validate_address(args.safe_address, field="--safe-address")
        validate_address(args.to, field="--to")
        validate_address(args.gas_token, field="--gas-token")
        validate_address(args.refund_receiver, field="--refund-receiver")
        validate_hex(args.data, field="--data")
        if args.nested_safe_address is not None:
            validate_address(args.nested_safe_address, field="--nested-safe-address")

        tx = SafeTx(
            to=args.to,
            value=args.value,
            data=args.data,
            operation=args.operation,
            safe_tx_gas=args.safe_tx_gas,
            base_gas=args.base_gas,
            gas_price=args.gas_price,
            gas_token=args.gas_token,
            refund_receiver=args.refund_receiver,
            nonce=args.nonce,
        )
        if nested:
            outer_version = args.nested_safe_version or args.safe_version
            result = nested_safe_hashes(
                chain_id=args.chain_id,
                inner_safe_address=args.safe_address,
                inner_safe_version=args.safe_version,
                inner_tx=tx,
                outer_safe_address=args.nested_safe_address,
                outer_safe_version=outer_version,
                outer_nonce=args.nested_safe_nonce,
            )
        else:
            result = safe_hashes(
                chain_id=args.chain_id,
                safe_address=args.safe_address,
                safe_version=args.safe_version,
                tx=tx,
            )
    except (ValueError, TypeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if nested:
        _print_nested_safe_hashes(result, args.output_json)
    else:
        _print_safe_hashes(result, args.output_json)


def _print_safe_hashes(h, output_json: bool) -> None:
    payload = {
        "domainHash": "0x" + h.domain_hash.hex(),
        "messageHash": "0x" + h.message_hash.hex(),
        "safeTxHash": "0x" + h.safe_tx_hash.hex(),
    }
    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        width = 42
        print(f"{'Domain Hash:':<{width}}{payload['domainHash']}")
        print(f"{'Message Hash:':<{width}}{payload['messageHash']}")
        print(f"{'Safe Transaction Hash (EIP-712 Digest):':<{width}}{payload['safeTxHash']}")


def _print_nested_safe_hashes(n, output_json: bool) -> None:
    inner = {
        "domainHash": "0x" + n.inner.domain_hash.hex(),
        "messageHash": "0x" + n.inner.message_hash.hex(),
        "safeTxHash": "0x" + n.inner.safe_tx_hash.hex(),
    }
    outer = {
        "domainHash": "0x" + n.outer.domain_hash.hex(),
        "messageHash": "0x" + n.outer.message_hash.hex(),
        "safeTxHash": "0x" + n.outer.safe_tx_hash.hex(),
    }
    if output_json:
        print(
            json.dumps(
                {
                    "inner": inner,
                    "outer": outer,
                    "approveHashCalldata": "0x" + n.approve_hash_calldata.hex(),
                },
                indent=2,
            )
        )
    else:
        width = 42
        print("Inner transaction")
        print(f"  {'Domain Hash:':<{width}}{inner['domainHash']}")
        print(f"  {'Message Hash:':<{width}}{inner['messageHash']}")
        print(f"  {'Safe Transaction Hash (EIP-712 Digest):':<{width}}{inner['safeTxHash']}")
        print()
        print("Outer transaction (approveHash on the inner Safe)")
        print(f"  {'Approve calldata:':<{width}}0x{n.approve_hash_calldata.hex()}")
        print(f"  {'Domain Hash:':<{width}}{outer['domainHash']}")
        print(f"  {'Message Hash:':<{width}}{outer['messageHash']}")
        print(f"  {'Safe Transaction Hash (EIP-712 Digest):':<{width}}{outer['safeTxHash']}")


def _handle_safe_msg(args: argparse.Namespace) -> None:
    from clearsig._safe_hash import safe_message_hashes
    from clearsig._validate import validate_address

    try:
        validate_address(args.safe_address, field="--safe-address")
        message: str = args.message if args.message is not None else args.message_file.read_text()
        h = safe_message_hashes(
            chain_id=args.chain_id,
            safe_address=args.safe_address,
            safe_version=args.safe_version,
            message=message,
        )
    except (OSError, ValueError, TypeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "rawMessageHash": "0x" + h.raw_message_hash.hex(),
        "domainHash": "0x" + h.domain_hash.hex(),
        "messageHash": "0x" + h.message_hash.hex(),
        "safeMessageHash": "0x" + h.safe_message_hash.hex(),
    }
    if args.output_json:
        print(json.dumps(payload, indent=2))
    else:
        width = 36
        print(f"{'Raw Message Hash:':<{width}}{payload['rawMessageHash']}")
        print(f"{'Domain Hash:':<{width}}{payload['domainHash']}")
        print(f"{'Message Hash:':<{width}}{payload['messageHash']}")
        print(f"{'Safe Message Hash (EIP-712 Digest):':<{width}}{payload['safeMessageHash']}")


def _handle_generate(args: argparse.Namespace) -> None:
    from clearsig._generate import generate_descriptor
    from clearsig._sourcify import fetch_abi
    from clearsig._validate import validate_address

    try:
        validate_address(args.to, field="--to")
        if args.abi:
            abi = json.loads(args.abi.read_text())
            if not isinstance(abi, list):
                raise ValueError(f"{args.abi} does not contain a JSON ABI list")
        else:
            abi, _visited, _match = fetch_abi(
                args.chain_id,
                args.to,
                base_url=args.sourcify_url,
                warn=lambda m: print(f"# {m}", file=sys.stderr),
            )

        descriptor = generate_descriptor(
            chain_id=args.chain_id,
            contract_address=args.to,
            abi=abi,
            owner=args.owner,
            legal_name=args.legal_name,
            url=args.url,
            schema_version="v2" if args.v2 else "v1",
        )
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps(descriptor, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    else:
        print(payload)
