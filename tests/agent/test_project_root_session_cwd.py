"""find_project_root() must honor the per-session cwd override.

Regression: it read ``scope_terminal_cwd()`` directly, skipping ``_SESSION_CWD``.
In a multiplexed gateway the per-turn terminal scope yields an EMPTY TERMINAL_CWD
when the profile's ``terminal.cwd`` is the ``.`` sentinel, so the direct read fell
through to ``Path.cwd()`` -- the GATEWAY's launch dir (``~/.hermes``), not the
chat's workspace. Every desktop session then resolved no project root and loaded
zero project skills, while a fresh-process probe in the same worktree resolved
correctly and reported health (which is what made it so hard to see).

Resolution order must be: _SESSION_CWD -> TERMINAL_CWD -> process cwd.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agent import skill_utils as su
from agent.runtime_cwd import clear_session_cwd, set_session_cwd


@pytest.fixture
def repo(tmp_path):
    """A real git repo (find_project_root looks for a .git entry)."""
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   capture_output=True)
    return root


@pytest.fixture(autouse=True)
def _clean_cwd_state():
    clear_session_cwd()
    yield
    clear_session_cwd()


def test_session_override_wins_over_empty_terminal_cwd(repo, tmp_path):
    """THE REGRESSION: empty TERMINAL_CWD + process cwd outside the project."""
    elsewhere = tmp_path / "gateway-launch-dir"
    elsewhere.mkdir()
    set_session_cwd(str(repo / "sub"))
    with patch.dict(os.environ, {"TERMINAL_CWD": ""}), \
            patch("agent.skill_utils.Path.cwd", return_value=elsewhere):
        assert su.find_project_root() == repo.resolve()


def test_session_override_wins_over_conflicting_terminal_cwd(repo, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    set_session_cwd(str(repo / "sub"))
    with patch.dict(os.environ, {"TERMINAL_CWD": str(other)}):
        assert su.find_project_root() == repo.resolve()


def test_terminal_cwd_still_used_without_session_override(repo):
    """Cron/API surfaces set TERMINAL_CWD without chdir'ing (#48975)."""
    clear_session_cwd()
    with patch.dict(os.environ, {"TERMINAL_CWD": str(repo / "sub")}):
        assert su.find_project_root() == repo.resolve()


def test_missing_session_dir_falls_back_to_terminal_cwd(repo):
    """A stale/deleted session cwd must not strand the session (or crash)."""
    set_session_cwd("/nonexistent/does/not/exist")
    with patch.dict(os.environ, {"TERMINAL_CWD": str(repo / "sub")}):
        assert su.find_project_root() == repo.resolve()


def test_non_project_session_cwd_resolves_nothing(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    set_session_cwd(str(plain))
    with patch.dict(os.environ, {"TERMINAL_CWD": ""}):
        assert su.find_project_root() is None
