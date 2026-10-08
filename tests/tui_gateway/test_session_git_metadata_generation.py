"""Gateway wiring for generation-scoped Git metadata publication."""

from __future__ import annotations

import tui_gateway.server as server


class _ImmediateThread:
    def __init__(self, *, target, **_kwargs):
        self._target = target

    def start(self):
        self._target()


def test_cwd_claim_precedes_probe_and_generation_reaches_publish(monkeypatch):
    events = []

    class DB:
        def update_session_cwd(self, session_id, cwd):
            events.append(("claim", session_id, cwd))
            return 17

        def publish_session_git_metadata(
            self, session_id, cwd, generation, branch, root
        ):
            events.append(
                ("publish", session_id, cwd, generation, branch, root)
            )
            return True

    monkeypatch.setattr(server, "_get_db", lambda: DB())
    monkeypatch.setattr(server.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        server.git_probe,
        "branch",
        lambda cwd: events.append(("probe", cwd)) or "feature",
    )
    monkeypatch.setattr(server.git_probe, "common_repo_root", lambda _cwd: "/repo")

    generation = server._persist_session_cwd_and_schedule_git_meta(
        {"session_key": "session"}, "/repo/worktree"
    )

    assert generation == 17
    assert events == [
        ("claim", "session", "/repo/worktree"),
        ("probe", "/repo/worktree"),
        (
            "publish",
            "session",
            "/repo/worktree",
            17,
            "feature",
            "/repo",
        ),
    ]


def test_missing_db_claim_never_starts_git_probe(monkeypatch):
    probed = []
    monkeypatch.setattr(server, "_get_db", lambda: None)
    monkeypatch.setattr(
        server.git_probe, "branch", lambda cwd: probed.append(cwd)
    )

    generation = server._persist_session_cwd_and_schedule_git_meta(
        {"session_key": "session"}, "/repo"
    )

    assert generation is None
    assert probed == []


class _FakeDB:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get_session(self, session_id):
        return dict(self._row) if self._row else None

    def update_session_cwd(self, session_id, cwd, git_branch=None, git_repo_root=None, replace_git_meta=False):
        return 42

    def publish_session_git_metadata(self, session_id, cwd, generation, branch, root):
        return True


def _run_backstop(monkeypatch, row, publish=None):
    calls = []

    def fake_claim(session, cwd, *, db=None):
        calls.append(cwd)
        return 42 if row else None

    monkeypatch.setattr(server, "_session_db", lambda session: _FakeDB(row))
    monkeypatch.setattr(server, "_persist_session_cwd_and_schedule_git_meta", fake_claim)
    session = {"session_key": "s1", "cwd": "/repo"}
    server._ensure_session_git_meta(session)
    return calls, session


def test_backstop_claims_when_row_has_no_metadata(monkeypatch):
    row = {"git_branch": None, "git_metadata_generation": 0, "cwd": "/repo"}
    calls, session = _run_backstop(monkeypatch, row)
    assert calls == ["/repo"]
    assert session["_git_meta_settled"] is True


def test_backstop_skips_rows_already_published_or_claimed(monkeypatch):
    for row in ({"git_branch": "main", "git_metadata_generation": 1},
                {"git_branch": "", "git_metadata_generation": 3}):
        calls, session = _run_backstop(monkeypatch, dict(row))
        assert calls == []
        assert session.get("_git_meta_settled") is True


def test_backstop_retries_while_row_absent(monkeypatch):
    calls, session = _run_backstop(monkeypatch, None)
    assert calls == []
    assert not session.get("_git_meta_settled")  # no claim, no settle: next turn retries
