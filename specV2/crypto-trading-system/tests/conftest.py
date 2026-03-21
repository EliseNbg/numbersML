"""Pytest configuration and fixtures."""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent
