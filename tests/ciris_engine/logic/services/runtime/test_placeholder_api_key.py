"""Never dial OpenAI with a key we can see is a placeholder.

On a live install `OPENAI_API_KEY=sk-test` (7 characters) was registered as a
working provider. Nothing noticed until something needed the model — and the
first thing that did was the SHUTDOWN deliberation, because the agent reasons
about accepting shutdown. So merely stopping the agent produced:

    LLM UNEXPECTED ERROR - InstructorRetryException
    Error code: 401 - Incorrect API key provided: sk-test
    DSDMA Ally evaluation failed for thought ID th_seed_SHUTDOWN_…
    CSDMA evaluation failed for thought ID th_seed_SHUTDOWN_…
    DMA 'ethical_pdma' failed: run_pdma failed after 3 attempts

from a user who had asked the agent nothing at all. Health had reported
`provider=openai` READY throughout, because readiness checked configuration
rather than whether the credential could authenticate.

THE FALSE POSITIVE THAT MATTERS MORE THAN THE BUG. Local runtimes are handed
placeholder keys ON PURPOSE — Ollama and llama.cpp ignore the value, so
`api_key="ollama"` against `jetson.local:11434` is CORRECT configuration, not a
mistake. A check that broke local inference to catch a cloud typo would be a bad
trade, so the guard only fires for keys bound to the real OpenAI endpoint.
Half the cases below exist to pin that.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.services.runtime.llm_service.service import _is_placeholder_api_key


@pytest.mark.parametrize(
    "key,base_url,why",
    [
        ("sk-test", None, "the exact key from the live install"),
        ("sk-test", "https://api.openai.com/v1", "same, with the endpoint stated"),
        ("changeme", None, "placeholder literal"),
        ("your-api-key-here", None, "placeholder literal"),
        ("SK-TEST", None, "case-insensitive"),
        ("  sk-test  ", None, "whitespace-padded"),
        ("sk-abc", None, "truncated sk- key: far below any issued length"),
    ],
)
def test_obvious_placeholders_are_refused(key: str, base_url: str | None, why: str) -> None:
    assert _is_placeholder_api_key(key, base_url) is True, why


@pytest.mark.parametrize(
    "key,base_url,why",
    [
        ("sk-" + "a" * 48, None, "a real-shaped OpenAI key"),
        ("sk-proj-" + "b" * 60, None, "a project key"),
        ("sk-" + "a" * 48, "https://api.openai.com/v1", "real key, explicit endpoint"),
        ("", None, "empty is the EXISTING guard's job; double-handling would change its error"),
        ("ollama", "http://jetson.local:11434/v1", "LOCAL runtime — dummy key is correct config"),
        ("none", "http://127.0.0.1:8000/v1", "local llama.cpp ignores the key entirely"),
        ("sk-test", "https://api.together.xyz/v1", "third-party endpoint — not ours to judge"),
        ("gsk_" + "c" * 40, "https://api.groq.com/openai/v1", "groq key, different shape"),
        ("sk-test-but-actually-a-very-long-real-key-000000", None, "CONTAINS a placeholder but is long"),
    ],
)
def test_everything_else_is_left_alone(key: str, base_url: str | None, why: str) -> None:
    assert _is_placeholder_api_key(key, base_url) is False, why


def test_the_refusal_names_the_problem_without_printing_the_key() -> None:
    """The error must not echo the credential slot's contents.

    `sk-test` is harmless, but this code path cannot know that — whatever sits
    in that variable is a credential by contract, and a log line does not get to
    assume otherwise. Length is the diagnostic; the value is not.
    """
    import inspect

    from ciris_engine.logic.services.runtime.llm_service import service

    src = inspect.getsource(service.OpenAICompatibleClient.__init__)
    guard = src[src.index("_is_placeholder_api_key") :][:900]
    assert "len(api_key" in guard, "length is what makes the message actionable"
    assert "{api_key}" not in guard, "must never interpolate the key itself into the message"
