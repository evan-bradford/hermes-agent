"""Tests for the interim_assistant_callback config gating in tui_gateway.

These tests exercise the real _agent_cbs() wiring rather than a local
imitation, so a break in the production callback registration is caught.
"""

from __future__ import annotations

from unittest.mock import patch


def test_load_interim_assistant_messages_defaults_true():
    from tui_gateway.server import _load_interim_assistant_messages

    with patch("tui_gateway.server._load_cfg", return_value={}):
        assert _load_interim_assistant_messages() is True


def test_agent_cbs_includes_interim_callback_when_enabled():
    """_agent_cbs() includes interim_assistant_callback when the config is on.

    Exercises the real _agent_cbs() wiring: the callback must be present in
    the returned dict and, when invoked, must emit a message.interim event
    with the text and already_streamed flag passed through.
    """
    from tui_gateway.server import _agent_cbs

    emitted: list[tuple] = []

    def fake_emit(event_type, sid, payload=None):
        emitted.append((event_type, sid, payload))

    with patch("tui_gateway.server._load_cfg", return_value={}), \
         patch("tui_gateway.server._emit", side_effect=fake_emit):
        cbs = _agent_cbs("test-session")

        assert "interim_assistant_callback" in cbs
        cb = cbs["interim_assistant_callback"]
        assert callable(cb)

        # Invoke the real callback inside the patch context — the lambda
        # resolves _emit by name at call time, so it must be called while
        # the patch is active.
        cb("hello world", already_streamed=True)

    assert len(emitted) == 1
    assert emitted[0][0] == "message.interim"
    assert emitted[0][1] == "test-session"
    assert emitted[0][2]["text"] == "hello world"
    assert emitted[0][2]["already_streamed"] is True




def _commentary_tool_turn() -> list[dict]:
    commentary = "I'll inspect the persisted transcript first."
    return [
        {
            "role": "assistant",
            "content": "",
            "reasoning": f"Need to inspect the display projection.\n\n{commentary}",
            "codex_message_items": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": commentary}],
                }
            ],
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "tool_name": "read_file",
            "content": '{"content":"ok"}',
        },
    ]

def test_history_projection_keeps_codex_commentary_tool_turn_visible():
    """Reloading a tool turn must not erase commentary shown live as interim."""
    from tui_gateway.server import _history_to_messages

    messages = _history_to_messages(_commentary_tool_turn())

    assert messages[0]["role"] == "assistant"
    assert messages[0]["text"] == "I'll inspect the persisted transcript first."
    assert messages[0]["reasoning"] == "Need to inspect the display projection."
    assert messages[1]["role"] == "tool"
    assert messages[1]["name"] == "read_file"
