"""Worktree trust inheritance must be decided per PROFILE, never pinned process-wide.

Regression: ``_inherits_trust_from_parent_repo`` was ``lru_cache``d on the path alone,
so it cached the trust VERDICT. One backend process serves every profile. Whichever
profile looked a new worktree up first decided it for all of them: a lookup made under
a profile that trusts nothing (e.g. an unscoped desktop request resolving to the default
profile) pinned the lane untrusted, and the profile that DOES trust the repo then loaded
no repo-only skills (no preflight, no router) for the life of the process, while its
same-named profile skills still loaded, so the session read as healthy.

A failed git probe (e.g. a lookup racing ``git worktree add``) must likewise not be
remembered as "not a worktree".
"""

import subprocess
from pathlib import Path

import pytest

from agent import skill_utils as su
from hermes_constants import reset_hermes_home_override, set_hermes_home_override


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def repo_with_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / ".hermes" / "skills" / "router").mkdir(parents=True)
    (repo / ".hermes" / "skills" / "router" / "SKILL.md").write_text(
        "---\nname: router\ndescription: test\n---\nbody\n")
    _git("add", ".", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=repo)
    wt = repo / ".worktrees" / "lane"
    _git("worktree", "add", "-q", "-b", "lane", str(wt), cwd=repo)
    return repo, wt


def _profile(home: Path, trusted: list) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    lines = ["skills:", "  trusted_project_dirs:"] + [f"    - {p}" for p in trusted]
    if not trusted:
        lines[-1] = "  trusted_project_dirs: []"
    (home / "config.yaml").write_text("\n".join(lines) + "\n")
    return home


@pytest.fixture(autouse=True)
def _fresh_caches():
    su._worktree_parent_cached.cache_clear()
    su._raw_config_cache_clear()
    yield
    su._worktree_parent_cached.cache_clear()
    su._raw_config_cache_clear()


def _trusted_under(home: Path, root: Path) -> bool:
    token = set_hermes_home_override(str(home))
    try:
        return su.is_project_root_trusted(root)
    finally:
        reset_hermes_home_override(token)


def test_untrusting_profile_asking_first_does_not_pin_the_lane(repo_with_worktree, tmp_path):
    """THE REGRESSION: profile order must not decide the verdict."""
    repo, wt = repo_with_worktree
    other = _profile(tmp_path / "default", [])
    owner = _profile(tmp_path / "sfb", [str(repo)])
    assert _trusted_under(other, wt) is False
    assert _trusted_under(owner, wt) is True
    assert _trusted_under(other, wt) is False  # and never leaks the other way


def test_trust_added_later_is_seen_without_restart(repo_with_worktree, tmp_path):
    repo, wt = repo_with_worktree
    home = _profile(tmp_path / "p", [])
    assert _trusted_under(home, wt) is False
    _profile(home, [str(repo)])
    su._raw_config_cache_clear()  # the config reader's own mtime cache, not the trust cache
    assert _trusted_under(home, wt) is True


def test_failed_git_probe_is_not_cached(tmp_path, monkeypatch):
    calls = []

    def boom(root):
        calls.append(root)
        raise su._GitProbeFailed("simulated race with git worktree add")

    monkeypatch.setattr(su, "_linked_worktree_parent", boom)
    assert su._inherits_trust_from_parent_repo(str(tmp_path)) is False
    assert su._inherits_trust_from_parent_repo(str(tmp_path)) is False
    assert len(calls) == 2  # retried, not remembered


def test_main_checkout_never_inherits(repo_with_worktree, tmp_path):
    repo, _ = repo_with_worktree
    home = _profile(tmp_path / "p", [str(repo / "nowhere")])
    assert _trusted_under(home, repo) is False


def test_worktree_of_untrusted_repo_is_not_promoted(repo_with_worktree, tmp_path):
    _, wt = repo_with_worktree
    home = _profile(tmp_path / "p", [str(tmp_path / "some-other-repo")])
    assert _trusted_under(home, wt) is False
