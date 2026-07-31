"""The preflight is only useful if it validates the endpoint the AGENT will use.

The load-bearing test here is `test_base_urls_match_kotlin_client`: it parses
LLMSettingsViewModel.kt so the Python table cannot silently drift from the
client's resolution. If they drift, the preflight green-lights one endpoint
while the agent calls another — worse than having no preflight, because it
reports confidence it has not earned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.qa_runner.modules.mobile.llm_preflight import PROVIDER_BASE_URLS, preflight_llm

KOTLIN = (
    Path(__file__).resolve().parents[3]
    / "client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/viewmodels/LLMSettingsViewModel.kt"
)


def test_base_urls_match_kotlin_client():
    """Python's provider->base_url table must match the client's."""
    if not KOTLIN.exists():
        pytest.skip(f"client source not present: {KOTLIN}")

    # Matches:  "openrouter" -> "https://openrouter.ai/api/v1"
    pairs = dict(re.findall(r'"([a-z]+)"\s*->\s*"(https://[^"]+)"', KOTLIN.read_text()))
    assert pairs, "parsed no provider->url pairs; the Kotlin shape changed and this guard is now blind"

    for provider, url in pairs.items():
        assert provider in PROVIDER_BASE_URLS, (
            f"client resolves {provider!r} but the preflight does not know it — "
            f"a filmstrip using --llm-provider {provider} would validate nothing"
        )
        assert PROVIDER_BASE_URLS[provider] == url, (
            f"DRIFT for {provider!r}: preflight validates {PROVIDER_BASE_URLS[provider]}, "
            f"client calls {url}. The preflight would pass while the agent fails."
        )


def test_missing_key_fails_closed():
    ok, msg = preflight_llm("openrouter", None, "meta-llama/llama-4-scout")
    assert not ok
    assert "no API key" in msg


def test_unknown_provider_fails_closed():
    ok, msg = preflight_llm("nope", "k", "m")
    assert not ok
    assert "unknown provider" in msg
    # The remediation must list what IS valid.
    assert "openrouter" in msg


def test_missing_model_fails_closed_and_warns_about_case():
    ok, msg = preflight_llm("together", "k", "")
    assert not ok
    # Case-collision is a real, costly failure on Together; the message must say so.
    assert "CASE-SENSITIVE" in msg


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "invalid or revoked"),
        (402, "out of credit"),
        (404, "Model not found"),
        (429, "Rate limited"),
    ],
)
def test_status_specific_remediation(monkeypatch, status, expected):
    """Each status must produce ITS OWN remediation, not a generic failure.

    402 vs 401 is the case that matters: both are 'the LLM did not answer', but
    one is a bad key and the other is a funded-account problem with a VALID key.
    Conflating them sends the operator to re-issue a key that was never wrong.
    """
    monkeypatch.setattr(
        "tools.qa_runner.modules.mobile.llm_preflight._post",
        lambda *a, **k: (status, '{"error": {"message": "provider detail here"}}'),
    )
    ok, msg = preflight_llm("together", "key", "google/gemma-4-31B-it")
    assert not ok
    assert expected in msg
    assert f"HTTP {status}" in msg
    assert "provider detail here" in msg, "the provider's own message must be surfaced verbatim"


def test_success_is_reported_with_endpoint(monkeypatch):
    monkeypatch.setattr(
        "tools.qa_runner.modules.mobile.llm_preflight._post",
        lambda *a, **k: (200, '{"choices":[{"message":{"content":"pong"}}]}'),
    )
    ok, msg = preflight_llm("openrouter", "key", "meta-llama/llama-4-scout")
    assert ok
    assert "openrouter.ai" in msg
