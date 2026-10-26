"""
Config Loader - YAML configuration loading, validation, and interpolation.

Loads hierarchical YAML configs for boards, test suites, and instruments,
with support for ``${ENV_VAR}`` interpolation and schema validation.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ENV_VAR_RE = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _interpolate_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` or ``${VAR:default}`` in strings."""
    if isinstance(value, str):
        def _replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            result = os.environ.get(var_name, default)
            if result is None:
                logger.warning("Environment variable '%s' is not set and has no default", var_name)
                return match.group(0)  # leave unchanged
            return result
        return _ENV_VAR_RE.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """Load and validate YAML configuration files."""

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._path: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: str | Path) -> dict[str, Any]:
        """Load a YAML config file, interpolate env-vars, and return the dict."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        self._config = _interpolate_env(raw)
        self._path = path
        logger.info("Loaded configuration from %s", path)
        return self._config

    def get_board_config(self, board_name: str) -> dict[str, Any]:
        """Return the configuration block for a specific board."""
        boards: dict[str, Any] = self._config.get("boards", {})
        if board_name in boards:
            return dict(boards[board_name])
        # Fallback to a "default" board or return minimal stub
        if "default" in boards:
            logger.info("Board '%s' not found — falling back to 'default'", board_name)
            return dict(boards["default"])
        logger.warning("No board config for '%s'; returning empty config", board_name)
        return {"platform": board_name}

    def get_suite_config(self, suite_name: str) -> dict[str, Any]:
        """Return the configuration block for a test suite."""
        suites: dict[str, Any] = self._config.get("suites", {})
        if suite_name in suites:
            return dict(suites[suite_name])
        logger.warning("Suite '%s' not found in configuration", suite_name)
        return {}

    def get_instrument_config(self, instrument: str) -> dict[str, Any]:
        """Return the configuration block for a test instrument."""
        instruments: dict[str, Any] = self._config.get("instruments", {})
        if instrument in instruments:
            return dict(instruments[instrument])
        logger.warning("Instrument '%s' not found in configuration", instrument)
        return {}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, config: dict[str, Any] | None = None, schema: dict[str, Any] | None = None) -> list[str]:
        """Validate *config* against an expected *schema* structure.

        *schema* maps dotted key paths to expected types, e.g.::

            {"boards": dict, "test_suites": list}

        Returns a list of validation error strings (empty if valid).
        """
        config = config or self._config
        if schema is None:
            # Minimal built-in schema
            schema = {
                "boards": dict,
                "test_suites": list,
            }

        errors: list[str] = []
        for key, expected_type in schema.items():
            parts = key.split(".")
            node: Any = config
            for part in parts:
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    node = None
                    break
            if node is None:
                errors.append(f"Missing required key: '{key}'")
            elif not isinstance(node, expected_type):
                errors.append(
                    f"Key '{key}' expected {expected_type.__name__}, got {type(node).__name__}"
                )

        if errors:
            logger.warning("Config validation found %d issue(s): %s", len(errors), "; ".join(errors))
        else:
            logger.info("Configuration validated successfully")
        return errors
