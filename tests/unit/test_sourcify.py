"""Unit tests for the Sourcify client (clearsig/_sourcify.py).

HTTP is mocked — no network calls.
"""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from unittest.mock import patch

import pytest

from clearsig._sourcify import fetch_abi


def _response(body: dict) -> io.BytesIO:
    """Build a fake urllib response object."""
    return io.BytesIO(json.dumps(body).encode())


def _make_urlopen(by_url: dict[str, dict]) -> object:
    """Build a urlopen mock that returns canned responses keyed by URL substring."""

    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for needle, body in by_url.items():
            if needle in url:
                return _response(body)
        raise AssertionError(f"unexpected URL: {url}")

    return fake_urlopen


TRANSFER_ABI = {
    "type": "function",
    "name": "transfer",
    "inputs": [
        {"name": "to", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
}
APPROVE_ABI = {
    "type": "function",
    "name": "approve",
    "inputs": [
        {"name": "spender", "type": "address"},
        {"name": "value", "type": "uint256"},
    ],
}


class TestFetchAbiSimple:
    def test_non_proxy_returns_abi_directly(self) -> None:
        responses = {
            "/0x1111111111111111111111111111111111111111": {
                "abi": [TRANSFER_ABI, APPROVE_ABI],
                "proxyResolution": {"isProxy": False, "implementations": []},
                "match": "exact_match",
            }
        }
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, match = fetch_abi(1, "0x1111111111111111111111111111111111111111")
        assert match == "exact_match"
        assert visited == ["0x1111111111111111111111111111111111111111"]
        assert len(abi) == 2
        assert {e["name"] for e in abi} == {"transfer", "approve"}

    def test_unverified_contract_raises(self) -> None:
        responses = {
            "/0x2222222222222222222222222222222222222222": {
                "abi": [],
                "proxyResolution": None,
                "match": None,
            }
        }
        with (
            patch("urllib.request.urlopen", _make_urlopen(responses)),
            pytest.raises(ValueError, match="not verified"),
        ):
            fetch_abi(1, "0x2222222222222222222222222222222222222222")

    def test_404_raises_helpful_error(self) -> None:
        def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", Message(), None)

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            pytest.raises(ValueError, match="not found on Sourcify"),
        ):
            fetch_abi(1, "0x3333333333333333333333333333333333333333")

    def test_500_raises_with_status(self) -> None:
        def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", Message(), None)

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            pytest.raises(ValueError, match="failed \\(500\\)"),
        ):
            fetch_abi(1, "0x4444444444444444444444444444444444444444")


class TestFetchAbiProxy:
    def test_single_proxy_hop(self) -> None:
        proxy_addr = "0x1111111111111111111111111111111111111111"
        impl_addr = "0x2222222222222222222222222222222222222222"
        responses = {
            proxy_addr: {
                "abi": [{"type": "function", "name": "upgradeTo", "inputs": []}],
                "proxyResolution": {
                    "isProxy": True,
                    "proxyType": "EIP1967Proxy",
                    "implementations": [{"address": impl_addr, "name": "Impl"}],
                },
                "match": "match",
            },
            impl_addr: {
                "abi": [TRANSFER_ABI, APPROVE_ABI],
                "proxyResolution": {"isProxy": False, "implementations": []},
                "match": "exact_match",
            },
        }
        warnings: list[str] = []
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, match = fetch_abi(1, proxy_addr, warn=warnings.append)

        assert visited == [proxy_addr, impl_addr]
        assert match == "match"  # proxy's match level
        names = {e["name"] for e in abi}
        # Both proxy's `upgradeTo` and impl's `transfer`/`approve` are present (deduped by selector)
        assert names == {"upgradeTo", "transfer", "approve"}
        assert any("EIP1967Proxy" in w for w in warnings)

    def test_multi_impl_unions_by_selector(self) -> None:
        """Diamond-style: proxy with multiple implementations; functions from all are merged."""
        proxy_addr = "0x1111111111111111111111111111111111111111"
        facet_a = "0x2222222222222222222222222222222222222222"
        facet_b = "0x3333333333333333333333333333333333333333"
        responses = {
            proxy_addr: {
                "abi": [],
                "proxyResolution": {
                    "isProxy": True,
                    "proxyType": "DiamondProxy",
                    "implementations": [
                        {"address": facet_a, "name": "FacetA"},
                        {"address": facet_b, "name": "FacetB"},
                    ],
                },
                "match": "exact_match",
            },
            facet_a: {
                "abi": [TRANSFER_ABI],
                "proxyResolution": {"isProxy": False, "implementations": []},
                "match": "exact_match",
            },
            facet_b: {
                "abi": [APPROVE_ABI],
                "proxyResolution": {"isProxy": False, "implementations": []},
                "match": "exact_match",
            },
        }
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, _ = fetch_abi(1, proxy_addr)

        assert set(visited) == {proxy_addr, facet_a, facet_b}
        assert {e["name"] for e in abi} == {"transfer", "approve"}

    def test_cycle_is_broken(self) -> None:
        """Proxy A points at B, B points at A. Each address is visited at most once."""
        a = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        b = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        responses = {
            a: {
                "abi": [],
                "proxyResolution": {
                    "isProxy": True,
                    "proxyType": "Test",
                    "implementations": [{"address": b, "name": "B"}],
                },
                "match": "match",
            },
            b: {
                "abi": [TRANSFER_ABI],
                "proxyResolution": {
                    "isProxy": True,
                    "proxyType": "Test",
                    "implementations": [{"address": a, "name": "A"}],
                },
                "match": "match",
            },
        }
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, _ = fetch_abi(1, a)
        # Visited each address once, didn't loop forever
        assert visited == [a, b]
        assert {e["name"] for e in abi} == {"transfer"}


class TestAddressValidation:
    @pytest.mark.parametrize(
        "address",
        [
            "not-an-address",
            "0x123",  # too short
            "0xZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",  # non-hex
        ],
    )
    def test_invalid_address_raises(self, address: str) -> None:
        with pytest.raises(ValueError, match="Invalid address"):
            fetch_abi(1, address)

    def test_uppercase_address_normalized(self) -> None:
        responses = {
            "/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
                "abi": [TRANSFER_ABI],
                "proxyResolution": None,
                "match": "exact_match",
            }
        }
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, _ = fetch_abi(1, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
        # Address is lowercased for the request
        assert visited == ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"]

    def test_address_without_0x_prefix_is_accepted(self) -> None:
        responses = {
            "/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
                "abi": [],
                "proxyResolution": None,
                "match": "exact_match",
            }
        }
        with patch("urllib.request.urlopen", _make_urlopen(responses)):
            abi, visited, _ = fetch_abi(1, "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
        assert visited == ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"]
