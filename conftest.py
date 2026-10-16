"""Tests must never load a developer's saved account or make real API calls."""
import os
import tempfile
from pathlib import Path

import httpx
import pytest

# Applied before test modules import main.app; fixtures run after those imports.
_bootstrap_config = tempfile.TemporaryDirectory(prefix="print-extractor-test-config-")
os.environ["PRINT_EXTRACTOR_CONFIG_PATH"] = str(Path(_bootstrap_config.name) / "settings.json")
os.environ["PRINT_EXTRACTOR_CLOUD_ENABLED"] = "0"


@pytest.fixture(autouse=True)
def isolated_ai_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINT_EXTRACTOR_CONFIG_PATH", str(tmp_path / "isolated-ai-settings.json"))
    for variable in ("PRINT_EXTRACTOR_CLOUD_ENABLED", "PRINT_EXTRACTOR_DASHSCOPE_API_KEY",
                     "PRINT_EXTRACTOR_DASHSCOPE_WORKSPACE"):
        monkeypatch.delenv(variable, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must use a mock/ASGI transport, never a real model API")

    async def no_async_network(*args, **kwargs):
        no_network()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_async_network)
