"""Tests for invocation-scoped TUI workspace overrides."""


def test_tui_launch_override_beats_profile_terminal_cwd(tmp_path, monkeypatch):
    from tui_gateway import server

    configured = tmp_path / "configured"
    override = tmp_path / "override"
    configured.mkdir()
    override.mkdir()

    monkeypatch.setattr(server, "_profile_configured_cwd", lambda _home: None)
    monkeypatch.setattr(server, "_launch_configured_cwd", lambda: str(configured))
    monkeypatch.setenv("_HERMES_CWD_OVERRIDE", str(override))

    assert server._completion_cwd() == str(override)
    assert server._default_session_cwd() == str(override)
