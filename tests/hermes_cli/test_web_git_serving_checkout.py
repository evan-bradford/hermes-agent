"""The desktop's branch switch never moves the checkout the backend runs from.

A sidebar lane's "+" switches the repo to the lane's branch before opening a chat.
On the source checkout the services import from, that rolled the running install
back to an old branch's code; worktrees and other repos keep switching as before.
"""

import os
import subprocess

import pytest

from hermes_cli import web_git


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "global.gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = (tmp_path / "checkout").resolve()
    root.mkdir()
    git(root, "init", "-q", "-b", "deploy")
    git(root, "-c", "user.name=T", "-c", "user.email=t@example.invalid",
        "commit", "-q", "--allow-empty", "-m", "base")
    git(root, "branch", "old")
    return root


def test_serving_checkout_refuses_switch_and_stays_put(repo, monkeypatch):
    monkeypatch.setattr(web_git, "_serving_root", lambda: repo)

    with pytest.raises(RuntimeError, match="serving this backend"):
        web_git.branch_switch(str(repo), "old")

    assert git(repo, "branch", "--show-current") == "deploy"


def test_serving_checkout_accepts_its_current_branch(repo, monkeypatch):
    monkeypatch.setattr(web_git, "_serving_root", lambda: repo)
    (repo / "pkg").mkdir()

    assert web_git.branch_switch(str(repo / "pkg"), "deploy") == {"branch": "deploy"}
    assert git(repo, "branch", "--show-current") == "deploy"


def test_worktree_of_serving_checkout_still_switches(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(web_git, "_serving_root", lambda: repo)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(wt))

    web_git.branch_switch(str(wt), "old")

    assert git(wt, "branch", "--show-current") == "old"
    assert git(repo, "branch", "--show-current") == "deploy"


def test_other_repo_switches_as_before(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(web_git, "_serving_root", lambda: (tmp_path / "elsewhere").resolve())

    web_git.branch_switch(str(repo), "old")

    assert git(repo, "branch", "--show-current") == "old"
