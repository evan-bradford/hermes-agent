"""Regression coverage for explicit chat workspace selection."""

import os
from types import SimpleNamespace


def test_agent_startup_applies_explicit_in_dir_before_discovery(tmp_path, monkeypatch):
    """Plugin/tool startup must observe the directory selected by ``--in``."""
    from hermes_cli import main

    launch_dir = tmp_path / "launch"
    target_dir = tmp_path / "target"
    launch_dir.mkdir()
    target_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.setenv("TERMINAL_CWD", str(launch_dir))

    # Keep the test focused on startup ordering; after the workspace is applied,
    # an unregistered command returns before plugin/MCP discovery begins.
    monkeypatch.setattr(main, "_AGENT_COMMANDS", set())
    monkeypatch.setattr(main, "_AGENT_SUBCOMMANDS", {})
    args = SimpleNamespace(
        command="chat",
        in_dir=str(target_dir),
        yolo=False,
        safe_mode=False,
    )

    main._prepare_agent_startup(args)

    assert launch_dir != target_dir
    assert target_dir.samefile(tmp_path.cwd())
    assert os.environ["TERMINAL_CWD"] == str(target_dir)
    assert args.no_restore_cwd is True
