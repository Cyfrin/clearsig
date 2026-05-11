"""End-to-end translation tests using the local registry."""

from eth_abi import encode

from clearsig import translate_with_registry
from clearsig._abi import compute_selector
from clearsig._registry import Registry


class TestTranslateERC20:
    def test_transfer(self, registry: Registry):
        selector = compute_selector("transfer", ["address", "uint256"])
        params = encode(
            ["address", "uint256"],
            ["0x000000000000000000000000000000000000dEaD", 1_000_000_000_000_000_000],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = translate_with_registry(
            registry,
            calldata,
            to="0x0000000000000000000000000000000000000001",
            chain_id=1,
        )

        assert result.intent == "Send"
        assert result.function_name == "transfer"
        assert result.function_signature == "transfer(address,uint256)"
        assert any(f.label == "Amount" for f in result.fields)
        assert any(f.label == "To" for f in result.fields)

    def test_approve_unlimited(self, registry: Registry):
        selector = compute_selector("approve", ["address", "uint256"])
        max_uint = 2**256 - 1
        params = encode(
            ["address", "uint256"],
            ["0x000000000000000000000000000000000000dEaD", max_uint],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = translate_with_registry(
            registry,
            calldata,
            to="0x0000000000000000000000000000000000000001",
            chain_id=1,
        )

        assert result.intent == "Approve"
        amount_field = next(f for f in result.fields if f.label == "Amount")
        assert amount_field.value == "Unlimited"


class TestTranslateAave:
    def test_supply(self, registry: Registry):
        selector = compute_selector("supply", ["address", "uint256", "address", "uint16"])
        params = encode(
            ["address", "uint256", "address", "uint16"],
            [
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
                1_000_000,  # 1 USDC (6 decimals)
                "0x000000000000000000000000000000000000dEaD",
                0,
            ],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = translate_with_registry(
            registry,
            calldata,
            to="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            chain_id=1,
        )

        assert result.intent == "Supply"
        assert result.entity in ("aave", "Aave")
        assert any(f.label == "Amount to supply" for f in result.fields)

    def test_borrow(self, registry: Registry):
        selector = compute_selector(
            "borrow", ["address", "uint256", "uint256", "uint16", "address"]
        )
        params = encode(
            ["address", "uint256", "uint256", "uint16", "address"],
            [
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                500_000,
                2,  # variable rate
                0,
                "0x000000000000000000000000000000000000dEaD",
            ],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = translate_with_registry(
            registry,
            calldata,
            to="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            chain_id=1,
        )

        assert result.intent == "Borrow"
        rate_field = next(f for f in result.fields if f.label == "Interest Rate mode")
        assert rate_field.value == "variable"


class TestTranslateSafe:
    def test_exec_transaction(self, registry: Registry):
        selector = compute_selector(
            "execTransaction",
            [
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
            ],
        )
        # Build a Safe execTransaction calling an ERC20 approve
        inner_selector = compute_selector("approve", ["address", "uint256"])
        inner_params = encode(
            ["address", "uint256"],
            ["0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2", 1_000_000],
        )
        inner_calldata = inner_selector + inner_params

        params = encode(
            [
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
            ],
            [
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # to (USDC)
                0,  # value
                inner_calldata,  # data (approve call)
                0,  # operation (Call)
                0,  # safeTxGas
                0,  # baseGas
                0,  # gasPrice
                "0x0000000000000000000000000000000000000000",  # gasToken
                "0x0000000000000000000000000000000000000000",  # refundReceiver
                b"",  # signatures
            ],
        )
        calldata = "0x" + selector.hex() + params.hex()

        result = translate_with_registry(
            registry,
            calldata,
            to="0x41675C099F32341bf84BFc5382aF534df5C7461a",
            chain_id=1,
            from_address="0x1234567890abcdef1234567890abcdef12345678",
        )

        assert result.intent == "sign multisig operation"
        assert result.entity in ("safe", "Safe")

        # Check operation field is formatted as enum
        op_field = next(f for f in result.fields if f.label == "Operation type")
        assert op_field.value == "Call"

        # Check transaction context fields
        safe_field = next(f for f in result.fields if f.label == "From Safe")
        assert safe_field.value == "0x41675C099F32341bf84BFc5382aF534df5C7461a"

        signer_field = next(f for f in result.fields if f.label == "Execution signer")
        assert signer_field.value == "0x1234567890abcdef1234567890abcdef12345678"

        # Check the nested calldata field is recursively decoded
        data_field = next(f for f in result.fields if f.label == "Transaction")
        assert "Approve" in data_field.value
        assert "approve(address,uint256)" in data_field.value
