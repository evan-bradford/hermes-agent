"""Codex discovery uses the same inherited credential scope as chat."""
import base64
import json
import time
from pathlib import Path

import pytest


def _token(label):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + 86400, "sub": label}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.mark.parametrize("profile_has_account", [False, True])
def test_catalog_uses_inherited_pool_without_overriding_profile_account(tmp_path, monkeypatch, profile_has_account):
    from hermes_cli import codex_models, models

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".hermes"
    profile = root / "profiles" / "sfb"
    profile.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(profile))
    global_token, profile_token = _token("global"), _token("profile")

    def auth(token, label):
        return {"version": 1, "providers": {}, "credential_pool": {"openai-codex": [{
            "id": label, "label": label, "auth_type": "oauth", "source": "manual:device_code",
            "access_token": token, "refresh_token": "test-refresh", "last_status": "ok",
        }]}}

    (root / "auth.json").write_text(json.dumps(auth(global_token, "global")))
    (profile / "auth.json").write_text(json.dumps(auth(profile_token, "profile") if profile_has_account else {"version": 1, "providers": {}}))
    seen = []
    visible = ["account-visible-model"]

    def fetch(token):
        seen.append(token)
        return visible

    monkeypatch.setattr(codex_models, "_fetch_models_from_api", fetch)
    result = models.provider_model_ids("openai-codex", force_refresh=True)
    assert result == visible
    assert seen == [profile_token if profile_has_account else global_token]
