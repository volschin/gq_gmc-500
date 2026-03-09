"""Tests for GMC-500 config flow.

Since homeassistant is not installed in the dev environment, we mock the
homeassistant modules via sys.modules before importing config_flow.py.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules so config_flow.py can be imported without HA
# ---------------------------------------------------------------------------

_ha_config_entries = MagicMock()


# Create base classes that our flow classes will inherit from
class _MockConfigFlow:
    """Mock ConfigFlow base class."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    async def async_set_unique_id(self, unique_id):
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass


class _MockOptionsFlow:
    """Mock OptionsFlow base class."""

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


_ha_config_entries.ConfigFlow = _MockConfigFlow
_ha_config_entries.OptionsFlow = _MockOptionsFlow
_ha_config_entries.ConfigFlowResult = dict

_ha_core = MagicMock()
_ha_core.callback = lambda f: f  # passthrough decorator

sys.modules.setdefault("homeassistant", MagicMock())
sys.modules.setdefault("homeassistant.config_entries", _ha_config_entries)
sys.modules.setdefault("homeassistant.core", _ha_core)

from custom_components.gmc500.config_flow import (  # noqa: E402
    GMC500ConfigFlow,
    GMC500OptionsFlow,
    test_port_available as check_port_available,
)
from custom_components.gmc500.const import (  # noqa: E402
    CONF_PORT,
    DEFAULT_PORT,
)


# ---------------------------------------------------------------------------
# Tests: test_port_available
# ---------------------------------------------------------------------------


class TestPortAvailable:
    """Tests for the test_port_available helper function."""

    def test_returns_true_when_port_is_free(self):
        """Port check returns True when bind succeeds."""
        with patch("custom_components.gmc500.config_flow.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            assert check_port_available(9999) is True
            mock_sock.bind.assert_called_once_with(("0.0.0.0", 9999))
            mock_sock.close.assert_called_once()

    def test_returns_false_when_port_in_use(self):
        """Port check returns False when bind raises OSError."""
        with patch("custom_components.gmc500.config_flow.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.bind.side_effect = OSError("Address already in use")
            mock_sock_cls.return_value = mock_sock
            assert check_port_available(9999) is False


# ---------------------------------------------------------------------------
# Tests: GMC500ConfigFlow — user step
# ---------------------------------------------------------------------------


class TestConfigFlowUserStep:
    """Tests for the user step of the config flow."""

    def _make_flow(self):
        """Create a config flow instance with a mocked hass."""
        flow = GMC500ConfigFlow()
        flow.hass = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_shows_form_when_no_input(self):
        """User step shows form when called without input."""
        flow = self._make_flow()
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_creates_entry_on_valid_port(self):
        """User step creates entry when port is available."""
        flow = self._make_flow()
        flow.hass.async_add_executor_job = AsyncMock(return_value=True)

        result = await flow.async_step_user(user_input={CONF_PORT: 8080})
        assert result["type"] == "create_entry"
        assert result["title"] == "GQ GMC-500"
        assert result["data"] == {CONF_PORT: 8080}

    @pytest.mark.asyncio
    async def test_shows_error_when_port_in_use(self):
        """User step shows error when port is not available."""
        flow = self._make_flow()
        flow.hass.async_add_executor_job = AsyncMock(return_value=False)

        result = await flow.async_step_user(user_input={CONF_PORT: 8080})
        assert result["type"] == "form"
        assert result["errors"] == {CONF_PORT: "port_in_use"}


# ---------------------------------------------------------------------------
# Tests: GMC500ConfigFlow — discovery step
# ---------------------------------------------------------------------------


class TestConfigFlowDiscoveryStep:
    """Tests for the discovery step of the config flow."""

    def _make_flow(self):
        """Create a config flow instance with a mocked hass."""
        flow = GMC500ConfigFlow()
        flow.hass = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_sets_unique_id_and_shows_confirm_form(self):
        """Discovery step sets unique_id and shows confirmation form."""
        flow = self._make_flow()
        discovery_data = {"aid": "0230111", "gid": "0034021", "cpm": 15}

        result = await flow.async_step_discovery(discovery_data)
        assert flow._unique_id == "0230111_0034021"
        assert result["type"] == "form"
        assert result["step_id"] == "discovery_confirm"

    @pytest.mark.asyncio
    async def test_confirm_creates_entry_with_custom_name(self):
        """Discovery confirm creates entry with user-provided name."""
        flow = self._make_flow()
        flow._discovery_data = {"aid": "0230111", "gid": "0034021", "cpm": 15}

        result = await flow.async_step_discovery_confirm(
            user_input={"name": "My Geiger Counter"}
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "My Geiger Counter"

    @pytest.mark.asyncio
    async def test_confirm_creates_entry_with_default_name(self):
        """Discovery confirm uses default name when none provided."""
        flow = self._make_flow()
        flow._discovery_data = {"aid": "0230111", "gid": "0034021", "cpm": 15}

        result = await flow.async_step_discovery_confirm(user_input={})
        assert result["type"] == "create_entry"
        assert result["title"] == "GMC-500 0034021"

    @pytest.mark.asyncio
    async def test_confirm_form_has_placeholders(self):
        """Discovery confirm form includes description placeholders."""
        flow = self._make_flow()
        flow._discovery_data = {"aid": "0230111", "gid": "0034021", "cpm": 15}

        result = await flow.async_step_discovery_confirm(user_input=None)
        assert result["description_placeholders"]["aid"] == "0230111"
        assert result["description_placeholders"]["gid"] == "0034021"
        assert result["description_placeholders"]["cpm"] == "15"


# ---------------------------------------------------------------------------
# Tests: GMC500OptionsFlow
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    """Tests for the options flow."""

    def _make_flow(self, current_port=DEFAULT_PORT):
        """Create an options flow with a mocked config entry."""
        config_entry = MagicMock()
        config_entry.data = {CONF_PORT: current_port}
        config_entry.options = {}
        flow = GMC500OptionsFlow(config_entry)
        flow.hass = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_shows_form_with_current_port(self):
        """Options step shows form with current port as default."""
        flow = self._make_flow(current_port=9090)
        result = await flow.async_step_init(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_saves_options_with_same_port(self):
        """Options step saves without port check when port unchanged."""
        flow = self._make_flow(current_port=8080)
        result = await flow.async_step_init(user_input={CONF_PORT: 8080})
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_PORT: 8080}

    @pytest.mark.asyncio
    async def test_validates_new_port(self):
        """Options step checks availability when port changes."""
        flow = self._make_flow(current_port=8080)
        flow.hass.async_add_executor_job = AsyncMock(return_value=True)

        result = await flow.async_step_init(user_input={CONF_PORT: 9090})
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_PORT: 9090}
        flow.hass.async_add_executor_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_error_when_new_port_in_use(self):
        """Options step shows error when new port is not available."""
        flow = self._make_flow(current_port=8080)
        flow.hass.async_add_executor_job = AsyncMock(return_value=False)

        result = await flow.async_step_init(user_input={CONF_PORT: 9090})
        assert result["type"] == "form"
        assert result["errors"] == {CONF_PORT: "port_in_use"}


# ---------------------------------------------------------------------------
# Tests: async_get_options_flow
# ---------------------------------------------------------------------------


class TestGetOptionsFlow:
    """Tests for the options flow factory."""

    def test_returns_options_flow_instance(self):
        """async_get_options_flow returns a GMC500OptionsFlow."""
        config_entry = MagicMock()
        result = GMC500ConfigFlow.async_get_options_flow(config_entry)
        assert isinstance(result, GMC500OptionsFlow)
        assert result.config_entry is config_entry
