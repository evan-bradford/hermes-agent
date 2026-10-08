"""MCP reload must retain the target session's profile and client surface.

Exercise the real registered handler and config loaders with isolated profile
files. Only external MCP transport and agent publication are replaced.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from hermes_constants import get_hermes_home, get_hermes_home_override
from tools import mcp_tool_agent, mcp_tool_config, mcp_tool_discovery, mcp_tool_lifecycle
from tui_gateway import server


@pytest.fixture
def reload_scope(tmp_path, monkeypatch):
    root = tmp_path / "hermes"
    work = root / "profiles" / "work"
    work.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(root))
    for key in ("HERMES_DESKTOP", "HERMES_DESKTOP_TERMINAL", "HERMES_TUI_TOOLSETS"):
        monkeypatch.delenv(key, raising=False)
    assert get_hermes_home_override() is None
    for home, name in ((root, "launch-only"), (work, "work-only")):
        (home / "config.yaml").write_text(yaml.safe_dump({
            "platform_toolsets": {"cli": ["file"]},
            "mcp_servers": {name: {"command": "fixture-not-executed"}},
        }))
    agent = SimpleNamespace(platform="desktop")
    session = {"agent": agent, "profile_home": str(work), "source": "desktop"}
    monkeypatch.setattr(server, "_sessions", {"scope-session": session})
    monkeypatch.setattr(server, "_session_uses_compute_host", lambda _: False)
    monkeypatch.setattr(server, "_session_info", lambda *_: {})
    monkeypatch.setattr(server, "_emit", lambda *_: None)
    monkeypatch.setattr(server, "_mcp_reload_gen", 0)
    monkeypatch.setattr(server, "_mcp_reload_loaded_rev", "")
    monkeypatch.setattr(mcp_tool_lifecycle, "shutdown_mcp_servers", lambda: None)
    monkeypatch.setattr(mcp_tool_agent, "reprobe_tool_availability", lambda: None)
    seen = {}

    def discover():
        seen["home"] = get_hermes_home()
        seen["servers"] = set(mcp_tool_config._load_mcp_config())
        return []

    def publish(_agent, *, enabled_override, quiet_mode):
        seen["toolsets"] = set(enabled_override)
        seen["publish_home"] = get_hermes_home()
        return set()

    monkeypatch.setattr(mcp_tool_discovery, "discover_mcp_tools", discover)
    monkeypatch.setattr(mcp_tool_agent, "refresh_agent_mcp_tools", publish)
    return root, work, session, seen, discover


@pytest.mark.parametrize("fail_discovery", [False, True])
def test_reload_uses_session_profile_and_restores_caller_scope(reload_scope, monkeypatch, fail_discovery):
    root, work, _session, seen, discover = reload_scope
    if fail_discovery:
        def fail():
            discover()
            raise RuntimeError("fixture transport failure")
        monkeypatch.setattr(mcp_tool_discovery, "discover_mcp_tools", fail)

    response = server.handle_request({
        "id": 1, "method": "reload.mcp",
        "params": {"session_id": "scope-session", "confirm": True},
    })
    assert response is not None

    assert seen["home"] == work
    assert seen["servers"] == {"work-only"}
    assert get_hermes_home() == root
    assert get_hermes_home_override() is None
    if fail_discovery:
        assert "error" in response
        assert "toolsets" not in seen
    else:
        assert response["result"]["status"] == "reloaded"
        assert seen["publish_home"] == work
        assert "work-only" in seen["toolsets"]
        assert "launch-only" not in seen["toolsets"]


def test_reload_keeps_desktop_tools_without_desktop_process_env(reload_scope):
    root, _work, session, seen, _discover = reload_scope
    session["profile_home"] = str(root)  # isolate the surface bug from profile routing
    response = server.handle_request({
        "id": 2, "method": "reload.mcp",
        "params": {"session_id": "scope-session", "confirm": True},
    })
    assert response is not None
    assert response["result"]["status"] == "reloaded"
    assert "desktop_ui" in seen["toolsets"]
