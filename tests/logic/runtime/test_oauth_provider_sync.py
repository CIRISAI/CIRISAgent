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


# ---------------------------------------------------------------------------
# The transport and the branches the tests above stub past.
#
# Everything above monkeypatches `_call`, which is right for asserting payload
# shape but leaves the HTTP layer and several decision branches unexercised —
# 53 uncovered lines, which is most of what this module is. These cover them
# against a real local HTTP server, so the request actually goes over a socket.
# ---------------------------------------------------------------------------

import http.server
import threading
from typing import Optional


class _Recorder(http.server.BaseHTTPRequestHandler):
    """Captures method/path/body and replies with whatever the test queued."""

    def _respond(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.seen.append((self.command, self.path, body))  # type: ignore[attr-defined]
        code, payload = self.server.reply  # type: ignore[attr-defined]
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_PUT = do_POST = _respond  # noqa: N815

    def log_message(self, *a: object) -> None:  # silence the test server
        return


@pytest.fixture
def server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    srv.seen = []            # type: ignore[attr-defined]
    srv.reply = (200, b"{}")  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _url(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}"


def test_call_really_sends_json_over_the_wire(server) -> None:
    """`_call` itself — stubbed out by every test above."""
    status, _ = sync._call("POST", _url(server) + "/x", {"a": 1})
    assert status == 200
    method, path, body = server.seen[-1]
    assert (method, path) == ("POST", "/x")
    assert json.loads(body) == {"a": 1}


def test_call_returns_the_status_on_an_http_error(server) -> None:
    """A 4xx must come back as a status, not raise — callers branch on it."""
    server.reply = (403, b'{"error":"no responsible party"}')  # type: ignore[attr-defined]
    status, body = sync._call("PUT", _url(server) + "/x", {"value": "v"})
    assert status == 403 and "responsible party" in body


def test_call_survives_an_unreachable_host() -> None:
    """Node down at boot must not raise — it is best-effort by contract."""
    status, detail = sync._call("GET", "http://127.0.0.1:1/nope")
    assert status == 0 and detail


def test_callback_base_is_skipped_when_already_correct(server, monkeypatch) -> None:
    """Idempotence: a matching GET means no write at all."""
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", "https://agents.ciris.ai")
    server.reply = (200, b'{"value":"https://agents.ciris.ai"}')  # type: ignore[attr-defined]

    sync._sync_callback_base(_url(server))

    assert not [c for c in server.seen if c[0] == "PUT"], "must not rewrite a correct value"


def test_callback_base_write_succeeds(server, monkeypatch, caplog) -> None:
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", "https://agents.ciris.ai/")
    server.reply = (200, b"{}")  # type: ignore[attr-defined]

    with caplog.at_level("INFO"):
        sync._sync_callback_base(_url(server))

    put = [c for c in server.seen if c[0] == "PUT"][-1]
    assert put[1].endswith("/v1/config/auth.oauth_callback_base_url")
    # Trailing slash stripped — the node concatenates the path onto this.
    assert json.loads(put[2]) == {"value": "https://agents.ciris.ai"}


def test_unexpected_status_on_the_config_write_is_reported(server, monkeypatch, caplog) -> None:
    """Neither 200 nor 403 — say the status rather than swallowing it."""
    monkeypatch.setenv("OAUTH_CALLBACK_BASE_URL", "https://agents.ciris.ai")
    server.reply = (500, b"{}")  # type: ignore[attr-defined]

    with caplog.at_level("WARNING"):
        sync._sync_callback_base(_url(server))

    assert "500" in caplog.text


def test_provider_without_credentials_is_skipped_not_posted(monkeypatch, caplog) -> None:
    """A malformed entry must not be sent as a half-configured provider."""
    monkeypatch.setattr(sync, "_read_provider_config", lambda: {"google": {"client_id": "cid"}})
    calls: List[Any] = []
    monkeypatch.setattr(sync, "_call", lambda *a, **k: calls.append(a) or (200, ""))
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)

    with caplog.at_level("WARNING"):
        sync.sync_oauth_providers_to_node("http://node")

    assert not calls
    assert "client_id/client_secret" in caplog.text


def test_non_dict_provider_entry_is_ignored(monkeypatch) -> None:
    """Hand-edited config: a string where an object belongs must not crash boot."""
    monkeypatch.setattr(sync, "_read_provider_config", lambda: {"google": "not-an-object"})
    calls: List[Any] = []
    monkeypatch.setattr(sync, "_call", lambda *a, **k: calls.append(a) or (200, ""))
    monkeypatch.delenv("OAUTH_CALLBACK_BASE_URL", raising=False)

    sync.sync_oauth_providers_to_node("http://node")
    assert not calls


def test_unreadable_config_file_reports_the_source_not_the_path(tmp_path, monkeypatch, caplog) -> None:
    """The read-failure branch, and the CodeQL property that fixed it.

    The log must name WHICH SOURCE was tried, never the path — a credential
    file's location is not the harmless part of a secrets file.
    """
    bad = tmp_path / "oauth.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(sync, "_SHARED_OAUTH_CONFIG", bad)
    monkeypatch.setattr(sync, "_LOCAL_OAUTH_CONFIG", tmp_path / "absent.json")

    with caplog.at_level("WARNING"):
        assert sync._read_provider_config() is None

    assert "shared volume" in caplog.text
    assert str(bad) not in caplog.text, "the path must never reach the log"


def test_config_read_prefers_the_shared_volume(tmp_path, monkeypatch) -> None:
    """Managed mode wins over the standalone fallback, as the old router did."""
    shared = tmp_path / "shared.json"
    local = tmp_path / "local.json"
    shared.write_text(json.dumps({"google": {"client_id": "S", "client_secret": "s"}}), encoding="utf-8")
    local.write_text(json.dumps({"google": {"client_id": "L", "client_secret": "l"}}), encoding="utf-8")
    monkeypatch.setattr(sync, "_SHARED_OAUTH_CONFIG", shared)
    monkeypatch.setattr(sync, "_LOCAL_OAUTH_CONFIG", local)

    assert sync._read_provider_config()["google"]["client_id"] == "S"
