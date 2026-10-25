"""Shared test helpers. Must not import Home Assistant."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent


def load_integration_models() -> ModuleType:
    """Import custom_components/syr_local/models.py without running the package __init__."""
    name = "syr_local_models_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO / "custom_components" / "syr_local" / "models.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


try:  # Integration tests need Home Assistant's test harness (Python 3.14).
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:
    collect_ignore = ["integration"]
