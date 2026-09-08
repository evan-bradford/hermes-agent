"""Client-facing projection helpers for model-only compaction carriers."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agent.context_compressor import ContextCompressor, is_compaction_summary_message


_COMPACTION_INTERNAL_FIELDS = (
    "tool_calls",
    "finish_reason",
    "reasoning",
    # Provider replay/metadata fields that ride the wire on every request but are invisible to
    # ``msg["content"]``/``msg["tool_calls"]`` accounting. Codex Responses sessions in particular carry
    # ``codex_reasoning_items`` blobs of ``encrypted_content`` that can dominate the serialized session (a
    # measured 214-turn session held ~115K tokens / 27% of its payload there — #55572).
    # ``reasoning_details`` is handled separately (see ``_reasoning_details_text_chars``): its signed/base64
    # envelope is excluded from the budget, mirroring the preflight estimator's exclusion in
    # ``model_metadata._estimate_message_tokens_without_images`` (#73298).
    # An assistant turn may carry only reasoning/thinking content with no visible text (extended-thinking
    # turns, thinking-only recovery responses). Such a turn is persisted with its reasoning fields and is
    # recallable from the transcript, but dropping it here as "empty" makes it vanish from the
    # resumed/reloaded session view while the desktop's reasoning disclosure has nothing to render. Keep it
    # when it carries reasoning so the "Thinking…" block still shows. (#44022)
    "reasoning_content",
    "reasoning_details",
    "codex_reasoning_items",
    "codex_message_items",
)


def project_compaction_message_for_display(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return authentic transcript content, or ``None`` for a pure handoff.

    Model-facing recovery history retains the complete carrier. Display
    projections instead remove the handoff, inherited tool state, and internal
    reasoning while preserving any real prior-tail content or live user ask
    embedded in the carrier.
    """
    if not isinstance(message, dict):
        return None
    if not is_compaction_summary_message(message):
        return message.copy()

    projected = ContextCompressor._strip_context_summary_handoff_message(message)
    if projected is None:
        return None

    projected = projected.copy()
    for key in _COMPACTION_INTERNAL_FIELDS:
        projected.pop(key, None)
    projected.pop("display_kind", None)
    return projected


def _codex_commentary_parts(value: Any) -> list[str]:
    """Decode user-visible ``phase=commentary`` Responses message items."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(value, list):
        return []

    messages: list[str] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        phase = item.get("phase")
        if not isinstance(phase, str) or phase.strip().lower() != "commentary":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        text = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "output_text"
        ).strip()
        if text:
            messages.append(text)
    return messages

def _remove_joined_reasoning_part(reasoning: str, part: str) -> str:
    """Remove one exact ``\n\n``-joined part without fuzzy text surgery."""
    if reasoning == part:
        return ""
    if reasoning.startswith(f"{part}\n\n"):
        return reasoning[len(part) + 2 :]
    if reasoning.endswith(f"\n\n{part}"):
        return reasoning[: -(len(part) + 2)]
    marker = f"\n\n{part}\n\n"
    if marker in reasoning:
        return reasoning.replace(marker, "\n\n", 1)
    return reasoning

def project_codex_commentary_for_display(message: Dict[str, Any]) -> Dict[str, Any]:
    """Promote designed-empty Codex commentary into display-only content.

    Codex Responses tool turns persist ``content: ""`` by design: their
    user-facing narration lives in exact ``codex_message_items`` so replay keeps
    provider ids/phases and prompt-cache continuity. The live gateway surfaces
    that narration through ``message.interim``. A later REST/resume hydration
    must project the same text back into the transcript without mutating the
    canonical model content, or the visible interim bubble disappears as soon
    as the persisted row replaces it.

    ``reasoning`` contains commentary too because normalization historically
    used that field as its fallback carrier. Remove only exact, paragraph-bound
    commentary parts from the display copy so expanding Thinking does not show
    the same prose twice; genuine reasoning remains intact.
    """
    projected = message.copy()
    if projected.get("role") != "assistant":
        return projected

    content = projected.get("content")
    if isinstance(content, str) and content.strip():
        return projected
    if isinstance(content, (list, dict)) and content:
        return projected

    commentary_parts = _codex_commentary_parts(projected.get("codex_message_items"))
    if not commentary_parts:
        return projected

    display_content = "\n\n".join(commentary_parts).strip()
    if not display_content:
        return projected

    from agent.redact import redact_sensitive_text

    projected["display_content"] = redact_sensitive_text(display_content)
    reasoning = projected.get("reasoning")
    if isinstance(reasoning, str) and reasoning:
        for part in commentary_parts:
            reasoning = _remove_joined_reasoning_part(reasoning, part)
        reasoning = reasoning.strip()
        if reasoning:
            projected["reasoning"] = reasoning
        else:
            projected.pop("reasoning", None)
    return projected
