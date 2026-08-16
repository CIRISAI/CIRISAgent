"""The agent must send the callback URL the provider console actually has.

THE REGRESSION THIS CLOSES (CIRISServer#421). Before the 2.9.14 auth fold,
`routes/auth.py` built the redirect_uri itself:

    OAUTH_CALLBACK_PATH = f"/v1/auth/oauth/{AGENT_ID}/{{provider}}/callback"

The fold moved OAuth into the node, whose port dropped the agent-id segment and
derived `{base}/v1/auth/oauth/{provider}/callback`. Two things then broke at
once: nginx does not route that path, and no console has it registered. Every
hosted Google sign-in answered `redirect_uri_mismatch`.

The node cannot fix this alone — it has no agent id to derive one from. From
0.5.176 `configure_provider` accepts `callback_url` and returns it verbatim, so
the agent, which does know its own id, sends the whole URL.

WHY THE AGENT-ID SEGMENT EXISTS AND WHY THE APP NEVER SEES IT. nginx routes the
public path and strips it before forwarding:

    location ~ ^/v1/auth/oauth/scout-remote-test-dahrb9/(.+)/callback$ {
        proxy_pass http://agent_.../v1/auth/oauth/$1/callback...;
    }

so one Google client serves the whole fleet, with a redirect URI registered per
agent, and the app only ever receives the two-segment form.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ciris_engine.logic.runtime import oauth_provider_sync as sync

#: Byte-for-byte what a live host has registered.
SCOUT_BASE = "https://scoutapilb.ciris.ai"
SCOUT_ID = "scout-remote-test-dahrb9"
SCOUT_URL = f"{SCOUT_BASE}/v1/auth/oauth/{SCOUT_ID}/google/callback"


@pytest.fixture
def hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", SCOUT_BASE)
    monkeypatch.setenv("CIRIS_AGENT_ID", SCOUT_ID)


def test_the_hosted_url_matches_what_nginx_routes(hosted: None) -> None:
    """Pinned verbatim — a provider compares this string exactly."""
    assert sync._hosted_callback_url("google") == SCOUT_URL


def test_a_trailing_slash_on_the_base_does_not_double(monkeypatch: pytest.MonkeyPatch) -> None:
    """`//v1/auth/...` is a different string to a provider, so it would mismatch."""
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", SCOUT_BASE + "/")
    monkeypatch.setenv("CIRIS_AGENT_ID", SCOUT_ID)
    assert sync._hosted_callback_url("google") == SCOUT_URL


@pytest.mark.parametrize(
    "base,agent_id",
    [("", SCOUT_ID), (SCOUT_BASE, ""), ("", "")],
)
def test_desktop_sends_nothing(monkeypatch: pytest.MonkeyPatch, base: str, agent_id: str) -> None:
    """A desktop install must keep the node's loopback default.

    RFC 8252: a natively-installed app is a public client and registers a
    loopback redirect. Sending a public URL there would break the one platform
    that never stopped working.
    """
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", base)
    monkeypatch.setenv("CIRIS_AGENT_ID", agent_id)
    assert sync._hosted_callback_url("google") is None


def test_the_url_is_NOT_taken_from_oauth_json(monkeypatch: pytest.MonkeyPatch, hosted: None) -> None:
    """THE TRAP. `oauth.json` carries a `callback_url`, and it is the wrong one.

    One Google client serves the fleet, so the provisioned file names whichever
    agent it was created for — on the scout hosts it reads `.../datum/...`.
    Forwarding that field would make every agent claim to be datum and stay
    broken, which is why this is built from the agent's OWN env instead.
    """
    calls: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        sync,
        "_read_provider_config",
        lambda: {
            "google": {
                "client_id": "cid",
                "client_secret": "sec",
                # datum's URL, deliberately present and deliberately ignored
                "callback_url": "https://agents.ciris.ai/v1/auth/oauth/datum/google/callback",
            }
        },
        raising=True,
    )
    monkeypatch.setattr(sync, "_sync_callback_base", lambda *a, **k: None, raising=True)

    def fake_call(method: str, url: str, body: Any = None) -> tuple:
        calls.append({"url": url, "body": body})
        return 200, "{}"

    monkeypatch.setattr(sync, "_call", fake_call, raising=True)

    sync.sync_oauth_providers_to_node("http://127.0.0.1:4243")

    posted = [c for c in calls if "providers" in c["url"]]
    assert posted, "provider was never registered"
    sent = posted[0]["body"]["callback_url"]
    assert sent == SCOUT_URL
    assert "datum" not in sent, "forwarded oauth.json's URL — every agent would claim to be datum"


def test_desktop_payload_omits_callback_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent, not empty — an empty string could be stored and returned verbatim."""
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("CIRIS_AGENT_ID", raising=False)
    calls: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        sync, "_read_provider_config", lambda: {"google": {"client_id": "c", "client_secret": "s"}}, raising=True
    )
    monkeypatch.setattr(sync, "_sync_callback_base", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(sync, "_call", lambda m, u, b=None: (calls.append({"u": u, "b": b}), (200, "{}"))[1], raising=True)

    sync.sync_oauth_providers_to_node("http://127.0.0.1:4243")

    posted = [c for c in calls if "providers" in c["u"]][0]
    assert "callback_url" not in posted["b"]


def test_the_secret_is_never_logged(monkeypatch: pytest.MonkeyPatch, hosted: None, caplog) -> None:
    """The payload carries a client_secret; a failure path must not echo it."""
    monkeypatch.setattr(
        sync, "_read_provider_config", lambda: {"google": {"client_id": "c", "client_secret": "TOPSECRET"}}, raising=True
    )
    monkeypatch.setattr(sync, "_sync_callback_base", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(sync, "_call", lambda m, u, b=None: (500, "error: TOPSECRET leaked"), raising=True)

    with caplog.at_level("INFO"):
        sync.sync_oauth_providers_to_node("http://127.0.0.1:4243")

    assert "TOPSECRET" not in caplog.text
