"""Defensive timestamp normalization for dashboard/API responses.

SQLite will faithfully return a numerically corrupt timestamp. Passing one
through to JavaScript is unsafe: ``Date`` accepts only a bounded millisecond
range, and ``toISOString()`` raises ``RangeError: Invalid time value`` for an
out-of-range value. Session recency also comes from ``MAX(messages.timestamp)``,
so one damaged message row can otherwise wedge the entire sessions surface.

Keep this at the API boundary. The database remains untouched (and therefore
diagnosable/recoverable), while every client receives a renderable value.
"""

from __future__ import annotations

import math
import time
from typing import Any, MutableMapping, Optional


# Session/message times should not lead the serving host by more than ordinary
# clock skew. This also sits many orders of magnitude inside JavaScript's Date
# ceiling, so values accepted here are safe to format in every Hermes client.
_MAX_FUTURE_SKEW_SECONDS = 24 * 60 * 60


def valid_unix_timestamp(value: Any, *, now: Optional[float] = None) -> Optional[float]:
    """Return *value* as finite epoch seconds, or ``None`` when implausible."""
    if isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    current = time.time() if now is None else float(now)
    if (
        not math.isfinite(seconds)
        or seconds <= 0
        or seconds > current + _MAX_FUTURE_SKEW_SECONDS
    ):
        return None
    return seconds


def normalize_session_timestamps(
    row: MutableMapping[str, Any], *, now: Optional[float] = None
) -> MutableMapping[str, Any]:
    """Make one session response row safe for arithmetic and date rendering.

    A damaged derived ``last_active`` falls back through the durable session
    heartbeat and creation time. Invalid optional timestamps become ``None``.
    The mutation is intentional: route handlers already annotate these response
    dictionaries in place.
    """
    current = time.time() if now is None else float(now)
    started = valid_unix_timestamp(row.get("started_at"), now=current) or current
    heartbeat = valid_unix_timestamp(row.get("last_activity_at"), now=current)
    last_active = (
        valid_unix_timestamp(row.get("last_active"), now=current)
        or heartbeat
        or started
    )

    row["started_at"] = started
    row["last_active"] = last_active
    if "last_activity_at" in row:
        row["last_activity_at"] = heartbeat

    for field in ("ended_at", "last_read_at", "turn_started_at"):
        if field in row:
            row[field] = valid_unix_timestamp(row.get(field), now=current)
    return row


def normalize_message_timestamp(
    row: MutableMapping[str, Any], *, now: Optional[float] = None
) -> MutableMapping[str, Any]:
    """Drop an invalid message timestamp from an API response.

    Timestamp-less messages already have explicit optimistic/display fallbacks
    in clients. Omitting a corrupt value is safer than manufacturing message
    chronology and prevents one damaged row from crashing transcript rendering.
    """
    if "timestamp" not in row:
        return row
    timestamp = valid_unix_timestamp(row.get("timestamp"), now=now)
    if timestamp is None:
        row.pop("timestamp", None)
    else:
        row["timestamp"] = timestamp
    return row
