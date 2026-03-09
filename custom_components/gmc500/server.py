"""HTTP server that receives data from GQ GMC-500 Geiger counters."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from aiohttp import web

from .const import (
    PARAM_AID,
    PARAM_GID,
    PARAM_CPM,
    PARAM_ACPM,
    PARAM_USV,
    PARAM_TMP,
    PARAM_HMDT,
    PARAM_AP,
    REQUIRED_PARAMS,
    OPTIONAL_PARAMS,
)

_LOGGER = logging.getLogger(__name__)

DataCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class GMCServer:
    """HTTP server that mimics gmcmap.com/log2.asp endpoint."""

    def __init__(self, port: int, data_callback: DataCallback) -> None:
        """Initialize the server."""
        self._port = port
        self._data_callback = data_callback
        self._app = web.Application()
        self._app.router.add_get("/log2.asp", self._handle_log2)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        """Start the HTTP server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()
        _LOGGER.info("GMC-500 server started on port %s", self._port)

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        _LOGGER.info("GMC-500 server stopped")

    async def _handle_log2(self, request: web.Request) -> web.Response:
        """Handle incoming log2.asp requests from GMC-500 devices."""
        params = request.query

        # Always respond OK.ERR0 to the device
        response = web.Response(text="OK.ERR0")

        # Validate required parameters
        for param in REQUIRED_PARAMS:
            if param not in params:
                _LOGGER.warning(
                    "Missing required parameter '%s' from %s",
                    param,
                    request.remote,
                )
                return response

        # Parse numeric values
        data: dict[str, Any] = {}
        try:
            data[PARAM_AID] = params[PARAM_AID]
            data[PARAM_GID] = params[PARAM_GID]
            data[PARAM_CPM] = float(params[PARAM_CPM])
            data[PARAM_ACPM] = float(params[PARAM_ACPM])
            data[PARAM_USV] = float(params[PARAM_USV])
        except (ValueError, KeyError) as err:
            _LOGGER.warning("Invalid parameter value: %s", err)
            return response

        # Parse optional parameters
        for param in OPTIONAL_PARAMS:
            if param in params:
                try:
                    data[param] = float(params[param])
                except ValueError:
                    _LOGGER.warning("Invalid optional parameter '%s': %s", param, params[param])

        # Call the data callback
        result = self._data_callback(data)
        if result is not None:
            await result

        return response
