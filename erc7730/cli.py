"""CLI for erc7730 calldata translation."""

import argparse
import json
import sys

from erc7730 import Registry, translate_with_registry, update_registry


def app() -> None:
    """Entry point for the erc7730 CLI."""
    parser = argparse.ArgumentParser(
        prog="erc7730",
        description="Translate EVM calldata to human-readable output using ERC-7730 descriptors.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # translate subcommand
    translate_parser = subparsers.add_parser(
        "translate", help="Translate raw calldata to human-readable output"
    )
    translate_parser.add_argument("calldata", help="Hex-encoded calldata (with or without 0x)")
    translate_parser.add_argument("--to", required=True, help="Contract address being called")
    translate_parser.add_argument(
        "--chain-id", type=int, default=1, help="Chain ID (default: 1)"
    )
    translate_parser.add_argument("--registry-path", help="Path to the ERC-7730 registry directory")
    translate_parser.add_argument("--from-address", help="Sender address for display context")
    translate_parser.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # update subcommand
    subparsers.add_parser("update", help="Download or update the ERC-7730 registry")

    args = parser.parse_args()

    if args.command == "translate":
        _handle_translate(args)
    elif args.command == "update":
        _handle_update()


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
