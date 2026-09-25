"""Shared fixtures for the core test suite."""
from __future__ import annotations

import pytest

from tests.helpers import install_fake_plugin


@pytest.fixture
def fake_plugin(monkeypatch):
    """Two made-up system setups (X1 long, X2 short) in place of whatever plugin
    is or is not installed. Yields their codes."""
    return install_fake_plugin(monkeypatch)
