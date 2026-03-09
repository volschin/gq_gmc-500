"""Test fixtures for GMC-500 integration."""

import pytest
from unittest.mock import patch


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.gmc500.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock
