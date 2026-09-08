"""Tests for invocation-scoped terminal workspace overrides."""

import os


def test_explicit_cwd_override_survives_terminal_config_bridge(tmp_path, monkeypatch):
    from hermes_cli import config
    from tools import terminal_tool

    configured = tmp_path / "configured"
    override = tmp_path / "override"
    configured.mkdir()
    override.mkdir()

    monkeypatch.setattr(terminal_tool, "_terminal_config_bridge_attempted", False)
    monkeypatch.setenv("_HERMES_CWD_OVERRIDE", str(override))
    monkeypatch.setenv("TERMINAL_CWD", str(override))
    monkeypatch.setattr(
        config,
        "read_raw_config",
        lambda: {"terminal": {"backend": "local", "cwd": str(configured)}},
    )

    def bridge_config(*, env=None, config=None, override=None):
        os.environ["TERMINAL_CWD"] = str(configured)

    monkeypatch.setattr(config, "apply_terminal_config_to_env", bridge_config)

    terminal_tool._ensure_terminal_env_bridged()

    assert os.environ["TERMINAL_CWD"] == str(override)


def test_explicit_cwd_override_reasserts_after_bridge_already_ran(
    tmp_path, monkeypatch
):
    from tools import terminal_tool

    configured = tmp_path / "configured"
    override = tmp_path / "override"
    configured.mkdir()
    override.mkdir()

    monkeypatch.setattr(terminal_tool, "_terminal_config_bridge_attempted", True)
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.setenv("TERMINAL_CWD", str(configured))
    monkeypatch.setenv("_HERMES_CWD_OVERRIDE", str(override))

    terminal_tool._ensure_terminal_env_bridged()

    assert os.environ["TERMINAL_CWD"] == str(override)
