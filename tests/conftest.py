import os
from pathlib import Path

import pytest

from erc7730._registry import Registry

REGISTRY_PATH = Path(__file__).parent.parent / "clear-signing-erc7730-registry"


@pytest.fixture(scope="session")
def registry_path() -> Path:
    if not REGISTRY_PATH.exists():
        pytest.skip("Local registry not available (clear-signing-erc7730-registry/)")
    return REGISTRY_PATH


@pytest.fixture(scope="session")
def registry(registry_path: Path) -> Registry:
    return Registry.from_path(registry_path)
