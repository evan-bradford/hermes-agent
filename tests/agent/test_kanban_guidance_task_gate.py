"""KANBAN_GUIDANCE is gated on an ASSIGNED TASK, not on kanban tool presence.

`kanban_show` is a member of the composite ``hermes-cli`` toolset, so any profile
selecting that composite (or selecting no toolsets at all, which enables everything)
exposes the kanban tools to ordinary interactive chats. Keying the dispatcher-worker
protocol off tool presence therefore injected ~6k chars of worker contract ("You have
been assigned ONE task", "you are running headless", "do not call clarify") into
sessions that have no task and DO have a live user.

Both resolution sites must apply the same gate: ``agent_init`` (the session-static
resolve) and the ``_tool_guidance`` fallback for code paths that bypass agent_init.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _tool_guidance(agent):
    from agent.system_prompt import _tool_guidance_block as fn

    return fn(agent) or ""


@pytest.fixture
def no_task_env():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HERMES_KANBAN_TASK", None)
        yield


@pytest.fixture
def task_env():
    with patch.dict(os.environ, {"HERMES_KANBAN_TASK": "t-42"}, clear=False):
        yield


# --- the fallback path in system_prompt._tool_guidance ----------------------


def test_fallback_omits_protocol_for_interactive_chat(no_task_env):
    """kanban tools present but NO assigned task: an interactive chat."""
    agent = SimpleNamespace(
        valid_tool_names={"kanban_show", "kanban_complete"},
        _kanban_worker_guidance=None,
    )
    assert "Kanban task execution protocol" not in _tool_guidance(agent)


def test_fallback_includes_protocol_for_dispatched_worker(task_env):
    """kanban tools AND an assigned task: a genuine dispatcher-spawned worker."""
    agent = SimpleNamespace(
        valid_tool_names={"kanban_show", "kanban_complete"},
        _kanban_worker_guidance=None,
    )
    assert "Kanban task execution protocol" in _tool_guidance(agent)


def test_fallback_omits_protocol_without_tools_even_with_task(no_task_env):
    """No kanban tools: nothing to brief, regardless of env."""
    agent = SimpleNamespace(valid_tool_names={"terminal"}, _kanban_worker_guidance=None)
    with patch.dict(os.environ, {"HERMES_KANBAN_TASK": "t-9"}):
        assert "Kanban task execution protocol" not in _tool_guidance(agent)


def test_precomputed_empty_string_is_respected(task_env):
    """agent_init's resolved "" must not be overridden by the fallback.

    The fallback triggers only on None (bypassed init); an explicit "" is a decision.
    """
    agent = SimpleNamespace(
        valid_tool_names={"kanban_show"},
        _kanban_worker_guidance="",
    )
    assert "Kanban task execution protocol" not in _tool_guidance(agent)


# --- the resolve site in agent_init ----------------------------------------


def test_hermes_cli_composite_exposes_kanban_show():
    """Regression guard on the premise: if this ever stops being true the gate is
    moot, but while it holds, tool presence cannot imply worker context."""
    from toolsets import resolve_toolset

    assert "kanban_show" in resolve_toolset("hermes-cli")
