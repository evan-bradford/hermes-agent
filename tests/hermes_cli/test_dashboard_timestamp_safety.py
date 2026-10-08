"""A corrupt durable timestamp must not wedge a dashboard client."""

from __future__ import annotations

import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_DASHBOARD_SESSION_TOKEN", "timestamp-test-token")

    import hermes_state
    from hermes_cli import web_server

    hermes_state.DEFAULT_DB_PATH = tmp_path / "state.db"
    with TestClient(web_server.app, raise_server_exceptions=False) as test_client:
        test_client.headers["Authorization"] = "Bearer timestamp-test-token"
        yield test_client, tmp_path


def test_session_and_transcript_routes_contain_corrupt_timestamp(client):
    test_client, home = client
    from hermes_state import SessionDB

    started_at = time.time() - 120
    db = SessionDB(db_path=home / "state.db")
    try:
        db.create_session("bad-time", source="desktop")
        db.append_message("bad-time", role="user", content="still recoverable")

        # The real incident was a finite but wildly out-of-range number, not
        # NaN. MAX(messages.timestamp) promoted it into session.last_active.
        def corrupt_timestamp(conn):
            conn.execute(
                "UPDATE sessions SET started_at = ? WHERE id = ?",
                (started_at, "bad-time"),
            )
            conn.execute(
                "UPDATE messages SET timestamp = ? WHERE session_id = ?",
                (1.0e100, "bad-time"),
            )

        db._execute_write(corrupt_timestamp)
    finally:
        db.close()

    response = test_client.get("/api/sessions", params={"min_messages": 1})
    assert response.status_code == 200
    row = next(item for item in response.json()["sessions"] if item["id"] == "bad-time")
    assert started_at - 1 <= row["last_active"] <= time.time() + 1

    response = test_client.get("/api/sessions/bad-time/messages")
    assert response.status_code == 200
    message = response.json()["messages"][0]
    assert message["content"] == "still recoverable"
    assert "timestamp" not in message
