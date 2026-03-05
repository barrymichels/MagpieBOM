"""Shared test fixtures for MagpieBOM test suite."""

import pytest
from tests.helpers import TINY_PNG


@pytest.fixture
def tiny_png_path(tmp_path):
    """Write TINY_PNG to a temp file and return its path as a string."""
    p = tmp_path / "test.png"
    p.write_bytes(TINY_PNG)
    return str(p)
