"""Unit tests for the 4byte.directory client (clearsig/_fourbyte.py).

HTTP is mocked — no network calls.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from clearsig._fourbyte import lookup_selector


def _make_urlopen(payload: dict) -> object:
    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        return io.BytesIO(json.dumps(payload).encode())

    return fake_urlopen


class _ReadLimitedResp:
    """A urlopen-like response that records what max_bytes was passed to read()."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.read_limit: int | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n: int | None = None) -> bytes:
        self.read_limit = n
        return self.body if n is None else self.body[:n]


APPROVE_RESPONSE = {
    "count": 4,
    "next": None,
    "previous": None,
    "results": [
        {"id": 313, "text_signature": "approve(address,uint256)", "hex_signature": "0x095ea7b3"},
        {
            "id": 822212,
            "text_signature": "sign_szabo_bytecode(bytes16,uint128)",
            "hex_signature": "0x095ea7b3",
        },
        {
            "id": 167,
            "text_signature": "older_collision()",
            "hex_signature": "0x095ea7b3",
        },
    ],
}


class TestLookupSelector:
    def test_returns_signatures_sorted_oldest_first(self):
        with patch("urllib.request.urlopen", _make_urlopen(APPROVE_RESPONSE)):
            sigs = lookup_selector("0x095ea7b3")
        # id 167 < 313 < 822212 → that's the order we want
        assert sigs == [
            "older_collision()",
            "approve(address,uint256)",
            "sign_szabo_bytecode(bytes16,uint128)",
        ]

    def test_accepts_selector_without_0x_prefix(self):
        with patch("urllib.request.urlopen", _make_urlopen(APPROVE_RESPONSE)):
            sigs = lookup_selector("095ea7b3")
        assert "approve(address,uint256)" in sigs

    def test_empty_results(self):
        with patch("urllib.request.urlopen", _make_urlopen({"results": []})):
            assert lookup_selector("0xdeadbeef") == []

    def test_rejects_non_hex_selector(self):
        with pytest.raises(ValueError, match="4 hex bytes"):
            lookup_selector("0xnothexx")

    def test_rejects_wrong_length(self):
        with pytest.raises(ValueError, match="4 hex bytes"):
            lookup_selector("0x095ea7")

    def test_filters_malicious_signatures(self):
        # A response that mixes legal signatures with ones containing ANSI
        # escapes or Unicode lookalikes — only the legal ones should come back.
        payload = {
            "results": [
                {"id": 1, "text_signature": "approve(address,uint256)"},
                {"id": 2, "text_signature": "approve(address,uint256)\x1b[2A"},
                {"id": 3, "text_signature": "аpprove(address,uint256)"},  # Cyrillic а
                {"id": 4, "text_signature": "transfer(address,uint256)"},
            ]
        }
        with patch("urllib.request.urlopen", _make_urlopen(payload)):
            sigs = lookup_selector("0x095ea7b3")
        assert sigs == ["approve(address,uint256)", "transfer(address,uint256)"]

    def test_caps_response_size(self):
        from clearsig._fourbyte import MAX_RESPONSE_BYTES

        body = json.dumps({"results": []}).encode()
        resp = _ReadLimitedResp(body)
        with patch("urllib.request.urlopen", return_value=resp):
            lookup_selector("0x095ea7b3")
        assert resp.read_limit == MAX_RESPONSE_BYTES + 1
