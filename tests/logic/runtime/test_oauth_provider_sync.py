"""The provider POST must carry EXACTLY the fields the node declares.

Two traps this pins, neither visible at runtime:

1. `configure_provider`'s payload struct has no `redirect_uri` field AND no
   `deny_unknown_fields`. Posting one is silently dropped and the node still
   answers `200 {"configured":"google"}` — a success that changes nothing while
   the callback keeps pointing at loopback. The callback is DERIVED from the
   `auth.oauth_callback_base_url` config key, never supplied here.

2. The request body carries a client secret. An error path that echoes the
   response, or a log line that includes the payload, leaks it.

Verified against a live node before these were written: the provider registers
and reads back as `{"providers":[{"client_id":…,"provider":"google"}]}`, and an
unowned node refuses the config key with 403.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest

from ciris_engine.logic.runtime import oauth_provider_sync as sync


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, str, Any]]:
    seen: List[Tuple[str, str, Any]] = []

    def fake(method: str, url: str, body: Any = None) -> Tuple[int, str]:
        seen.append((method, url, body))
        if "/v1/config/" in url:
            return (403, '{"error":"no responsible party"}')
        return (200, '{"configured":"google"}')

    monkeypatch.setattr(sync, "_call", fake)
    monkeypatch.setattr(
        sync, "_read_provider_config",
        lambda: {"google": {"client_id": "cid", "client_secret": "shhh"}},
    )
    return seen


def test_payload_is_exactly_the_declared_fields(calls, monkeypatch) -> None:
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)
    sync.sync_oauth_providers_to_node("http://node")

    post = next(c for c in calls if c[0] == "POST")
    assert post[1] == "http://node/v1/auth/oauth/providers"
    assert set(post[2]) == {"provider", "client_id", "client_secret", "metadata"}, (
        "the node's struct declares exactly these; an extra redirect_uri is dropped "
        "silently and the call still returns 200, so the mistake is invisible"
    )
    assert "redirect_uri" not in post[2]


def test_callback_base_is_written_to_the_config_key_not_the_provider(calls, monkeypatch) -> None:
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", "https://agents.ciris.ai")
    sync.sync_oauth_providers_to_node("http://node")

    puts = [c for c in calls if c[0] == "PUT"]
    assert puts, "the base must be set via the config key — it is not a provider field"
    assert puts[0][1].endswith("/v1/config/auth.oauth_callback_base_url")
    assert puts[0][2] == {"value": "https://agents.ciris.ai"}


def test_no_base_configured_means_no_config_write(calls, monkeypatch) -> None:
    """Desktop: the node's loopback default is CORRECT there, so leave it alone."""
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)
    sync.sync_oauth_providers_to_node("http://node")

    assert not [c for c in calls if c[0] == "PUT"]


def test_the_403_is_reported_once_and_does_not_raise(calls, monkeypatch, caplog) -> None:
    """An unowned node must not boot-loop, and must say what to do."""
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", "https://agents.ciris.ai")
    with caplog.at_level("WARNING"):
        sync.sync_oauth_providers_to_node("http://node")

    assert len([c for c in calls if c[0] == "PUT"]) == 1, "no retry loop"
    assert "403" in caplog.text and "claim" in caplog.text.lower()


def test_secrets_never_reach_the_log(monkeypatch, caplog) -> None:
    """Failure path: the body carried a secret; the log must not."""
    monkeypatch.setattr(sync, "_call", lambda m, u, b=None: (500, '{"err":"shhh leaked here"}'))
    monkeypatch.setattr(
        sync, "_read_provider_config",
        lambda: {"google": {"client_id": "cid", "client_secret": "shhh"}},
    )
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)

    with caplog.at_level("WARNING"):
        sync.sync_oauth_providers_to_node("http://node")

    assert "shhh" not in caplog.text, "neither the payload nor the response body may be logged"


def test_absent_config_file_is_normal(monkeypatch, caplog) -> None:
    """Every desktop install is in this state; it is not a failure."""
    monkeypatch.setattr(sync, "_read_provider_config", lambda: None)
    called: List[Any] = []
    monkeypatch.setattr(sync, "_call", lambda *a, **k: called.append(a) or (200, ""))

    sync.sync_oauth_providers_to_node("http://node")

    assert not called
