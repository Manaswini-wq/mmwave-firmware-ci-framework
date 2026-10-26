"""Tests for YAML configuration parsing and validation.

Covers loading, schema validation, board lookup, and environment
variable interpolation in configuration files.
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
import yaml

from framework.core.config_loader import ConfigLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def config_loader() -> ConfigLoader:
    return ConfigLoader()


@pytest.fixture
def valid_config_file(tmp_path: Path) -> Path:
    """Create a minimal valid YAML configuration on disk."""
    cfg = tmp_path / "test_config.yaml"
    cfg.write_text(
        textwrap.dedent("""\
            project: mmwave-ci
            boards:
              AWR2944:
                platform: awr2944
                uart_port: COM3
                uart_baud: 115200
              IWR6843:
                platform: iwr6843
                uart_port: COM5
                uart_baud: 921600
            test_suites:
              - tests/unit
              - tests/integration
        """),
        encoding="utf-8",
    )
    return cfg


# ---------------------------------------------------------------------------
# Load tests
# ---------------------------------------------------------------------------

class TestConfigLoading:
    """YAML config file loading and schema verification."""

    @pytest.mark.config
    def test_load_valid_config(
        self, config_loader: ConfigLoader, valid_config_file: Path
    ) -> None:
        """A well-formed YAML file must load without error."""
        config = config_loader.load(valid_config_file)
        assert config["project"] == "mmwave-ci"
        assert "boards" in config
        assert len(config["test_suites"]) == 2

    @pytest.mark.config
    def test_load_invalid_config_raises(
        self, config_loader: ConfigLoader, tmp_path: Path
    ) -> None:
        """Loading a non-existent file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            config_loader.load(tmp_path / "does_not_exist.yaml")


# ---------------------------------------------------------------------------
# Board lookup tests
# ---------------------------------------------------------------------------

class TestBoardConfigLookup:
    """Board-specific configuration retrieval."""

    @pytest.mark.config
    def test_board_config_lookup(
        self, config_loader: ConfigLoader, valid_config_file: Path
    ) -> None:
        """Requesting a known board must return its config dict."""
        config_loader.load(valid_config_file)
        board_cfg = config_loader.get_board_config("AWR2944")
        assert board_cfg["platform"] == "awr2944"
        assert board_cfg["uart_baud"] == 115200

    @pytest.mark.config
    def test_unknown_board_raises(
        self, config_loader: ConfigLoader, valid_config_file: Path
    ) -> None:
        """Requesting an unknown board must raise KeyError."""
        config_loader.load(valid_config_file)
        with pytest.raises(KeyError):
            config_loader.get_board_config("UNKNOWN_DEVICE")


# ---------------------------------------------------------------------------
# Environment variable interpolation
# ---------------------------------------------------------------------------

class TestEnvVariableInterpolation:
    """${ENV_VAR} placeholders must be resolved at load time."""

    @pytest.mark.config
    def test_env_variable_interpolation(
        self, config_loader: ConfigLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables in config values must be expanded."""
        monkeypatch.setenv("CI_UART_PORT", "COM7")
        cfg = tmp_path / "env_config.yaml"
        cfg.write_text(
            textwrap.dedent("""\
                boards:
                  AWR2944:
                    platform: awr2944
                    uart_port: ${CI_UART_PORT}
            """),
            encoding="utf-8",
        )
        config = config_loader.load(cfg)
        assert config["boards"]["AWR2944"]["uart_port"] == "COM7"
