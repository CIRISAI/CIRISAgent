"""A fresh install must be able to list models with a valid key.

From a real user's log: seven consecutive
"[LIST_MODELS] Live query failed, falling back to static data" — with no
exception recorded. The wizard then presented the cached catalogue as though it
had been confirmed against their key, so the failure was invisible twice over:
once in the log, and once on screen.

The conformance matrix, run live, found two of six listings broken 100% of the
time on VALID credentials. Both are repaired here, and the diagnostic gap that
hid them is closed.
"""

import asyncio
import inspect
from typing import Any, List

import pytest

from ciris_engine.logic.adapters.api.routes.setup import llm_validation
from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationRequest


class TestAFailedListingSaysWhy:
    """A fallback nobody can diagnose is worse than an error — it looks like success."""

    @pytest.mark.asyncio
    async def test_the_exception_is_logged_not_swallowed(self, monkeypatch, caplog) -> None:
        async def boom(_config):
            raise RuntimeError("upstream exploded")

        monkeypatch.setattr(llm_validation, "_fetch_live_models", boom)
        with caplog.at_level("WARNING"):
            resp = await llm_validation._list_models_for_provider(
                LLMValidationRequest(provider="openrouter", api_key="k")
            )
        blob = caplog.text
        assert "RuntimeError" in blob, f"the exception TYPE must reach the log; got: {blob[-400:]}"
        assert "upstream exploded" in blob, "the provider's own words must reach the log"
        assert "openrouter" in blob, "which provider failed must reach the log"
        assert resp.source == "static"

    @pytest.mark.asyncio
    async def test_a_timeout_is_named_as_a_timeout(self, monkeypatch, caplog) -> None:
        """Nothing is misconfigured — the catalogue just did not arrive. Told
        apart, that is a retry; lumped in with a broken provider, a support ticket."""

        async def slow(_config):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(llm_validation, "_fetch_live_models", slow)
        with caplog.at_level("WARNING"):
            resp = await llm_validation._list_models_for_provider(
                LLMValidationRequest(provider="openrouter", api_key="k")
            )
        assert "TIMED OUT" in caplog.text
        assert "timed out" in (resp.error or "").lower()

    def test_the_timeout_is_generous_enough_for_a_large_catalogue(self) -> None:
        """OpenRouter serves ~420 models; 10s over a consumer link is not enough,
        and a timeout is indistinguishable from a broken provider to the user."""
        assert llm_validation._LIST_MODELS_TIMEOUT >= 30


class TestGoogleListingActuallyIterates:
    """`AsyncModels.list()` returns a COROUTINE, not an async iterable."""

    def test_the_pager_is_awaited_before_iterating(self) -> None:
        src = inspect.getsource(llm_validation._google_models_to_list)
        assert "await client.aio.models.list" in src, (
            "without the await this raises \"'async for' requires an object with __aiter__ "
            "method, got coroutine\" on every call — Google's listing failed 100% of the time"
        )
        assert "async for model in pager" in src

    @pytest.mark.asyncio
    async def test_it_collects_models_from_the_resolved_pager(self) -> None:
        class Model:
            def __init__(self, name): self.name = name

        class Pager:
            def __aiter__(self):
                async def gen():
                    yield Model("models/gemini-3.6-flash")
                return gen()

        class Models:
            async def list(self, config=None):  # coroutine, exactly like the SDK
                return Pager()

        class Client:
            aio = type("Aio", (), {"models": Models()})()

        got = await llm_validation._google_models_to_list(Client())
        assert [m.name for m in got] == ["models/gemini-3.6-flash"]


class TestANonStandardModelsEnvelopeStillLists:
    """Together answers /models with a bare array where the SDK expects
    {"data": [...]}, so the SDK's own parse raises AttributeError."""

    @pytest.mark.asyncio
    async def test_a_bare_array_response_is_read_directly(self, monkeypatch) -> None:
        class Models:
            async def list(self):
                raise AttributeError("'list' object has no attribute '_set_private_attributes'")

        class FakeClient:
            models = Models()

            async def get(self, path, cast_to=None):
                assert path == "/models"
                return [{"id": "meta-llama/Llama-4-Scout-17B-16E-Instruct"}, {"id": "other/model"}]

        monkeypatch.setattr(llm_validation, "AsyncOpenAI", lambda **kw: FakeClient(), raising=False)
        import openai

        monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: FakeClient())

        got = await llm_validation._list_models_openai_compatible("k", "https://api.together.xyz/v1")
        assert [m.id for m in got] == [
            "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "other/model",
        ]

    @pytest.mark.asyncio
    async def test_a_standard_envelope_still_uses_the_sdk_path(self, monkeypatch) -> None:
        class Entry:
            def __init__(self, i): self.id = i

        class Page:
            data = [Entry("gpt-4o"), Entry("o3")]

        class Models:
            async def list(self):
                return Page()

        class FakeClient:
            models = Models()

            async def get(self, path, cast_to=None):  # pragma: no cover
                raise AssertionError("should not fall back when the SDK parses")

        import openai

        monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: FakeClient())
        got = await llm_validation._list_models_openai_compatible("k", "https://api.openai.com/v1")
        assert [m.id for m in got] == ["gpt-4o", "o3"]
