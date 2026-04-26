"""Tests for `_try_recover_missing_brace` — Llama-family JSON-mode bug recovery.

Concrete failure mode (observed on `meta-llama/llama-4-scout` via OpenRouter
in instructor JSON mode): the model emits a JSON body that's missing its
leading `{`. Closing `}` is usually present. Instructor's parser fails with
"Invalid JSON: expected value at line 1 column 1". The recovery path
prepends `{` and re-parses — the body is otherwise well-formed.

Captured pattern:
    `"selected_action": "speak", "speak_content": "...", "reasoning": "..."}`

This caused the production agent to spin in retry loops, eventually opening
the circuit breaker. The recovery short-circuits that cascade.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import BaseModel

from ciris_engine.logic.services.runtime.llm_service.service import (
    _try_recover_missing_brace,
)


class _SampleResult(BaseModel):
    selected_action: str
    speak_content: str
    reasoning: str


def _make_exc(content: Optional[str]) -> Exception:
    """Build an exception with `last_completion.choices[0].message.content`
    matching the shape instructor.InstructorRetryException provides."""
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    completion = SimpleNamespace(choices=[choice])
    exc = RuntimeError("InstructorRetryException simulated")
    exc.last_completion = completion  # type: ignore[attr-defined]
    return exc


# ────────────────────────────── happy path ────────────────────────────────


def test_missing_leading_brace_recovered() -> None:
    """The canonical bug pattern — body without leading `{`, closing `}` present."""
    body = (
        '"selected_action": "speak", '
        '"speak_content": "Hi! How can I help?", '
        '"reasoning": "User greeted; respond in kind."}'
    )
    exc = _make_exc(body)

    result = _try_recover_missing_brace(exc, _SampleResult)

    assert result is not None
    parsed, _completion = result
    assert isinstance(parsed, _SampleResult)
    assert parsed.selected_action == "speak"
    assert parsed.speak_content == "Hi! How can I help?"
    assert parsed.reasoning == "User greeted; respond in kind."


def test_leading_whitespace_before_key_still_recovered() -> None:
    """The model often emits leading whitespace before the first key
    (e.g. `\n  "selected_action": ...`). Recovery strips correctly."""
    body = (
        '\n  "selected_action": "speak", '
        '"speak_content": "ok", '
        '"reasoning": "test"}'
    )
    exc = _make_exc(body)

    result = _try_recover_missing_brace(exc, _SampleResult)

    assert result is not None
    parsed, _ = result
    assert parsed.selected_action == "speak"


def test_attaches_completion_for_telemetry() -> None:
    """The recovered tuple includes the completion so the LLM service can
    still log token counts, timing, etc., as if the call had succeeded."""
    body = (
        '"selected_action": "speak", '
        '"speak_content": "ok", '
        '"reasoning": "test"}'
    )
    exc = _make_exc(body)

    result = _try_recover_missing_brace(exc, _SampleResult)

    assert result is not None
    _parsed, completion = result
    # Same completion object the exception carried
    assert completion is exc.last_completion  # type: ignore[attr-defined]


# ────────────────────────────── pass-through cases ───────────────────────


def test_already_valid_json_returns_none() -> None:
    """Content that's already a complete JSON object isn't this bug — bail
    out so the caller re-raises and the real error surfaces."""
    body = (
        '{"selected_action": "speak", '
        '"speak_content": "ok", '
        '"reasoning": "test"}'
    )
    exc = _make_exc(body)
    assert _try_recover_missing_brace(exc, _SampleResult) is None


def test_leading_brace_with_whitespace_returns_none() -> None:
    """`{` after some leading whitespace is also already-valid — not our bug."""
    body = (
        '  \n{"selected_action": "speak", '
        '"speak_content": "ok", '
        '"reasoning": "test"}'
    )
    exc = _make_exc(body)
    assert _try_recover_missing_brace(exc, _SampleResult) is None


def test_non_key_opening_returns_none() -> None:
    """If the response opens with prose, an array, or anything other than
    a key-colon pattern, it's a different bug (or not JSON at all). We
    don't try to be clever — bail out, let the caller surface the error."""
    for content in [
        "Sorry, I cannot help with that.",
        '["selected_action", "speak"]',
        '"just a string"',
        "}",          # the one-character truncation case from the prod log
        "null",
        "12345",
    ]:
        exc = _make_exc(content)
        assert _try_recover_missing_brace(exc, _SampleResult) is None, (
            f"unexpected recovery on content: {content!r}"
        )


def test_empty_content_returns_none() -> None:
    """Empty / None content can't be recovered."""
    for content in [None, "", "   ", "\n\n"]:
        exc = _make_exc(content)
        assert _try_recover_missing_brace(exc, _SampleResult) is None


def test_no_last_completion_returns_none() -> None:
    """If the exception has no `last_completion` attribute, no recovery."""
    exc = RuntimeError("opaque error")
    assert _try_recover_missing_brace(exc, _SampleResult) is None


def test_recovered_string_that_fails_pydantic_validation_returns_none() -> None:
    """Even with leading `{` prepended, if the body doesn't validate against
    the response_model (e.g. wrong field types, missing required fields),
    recovery fails — caller re-raises the original error rather than
    masking it with a less-informative validation error."""
    body = (
        '"selected_action": "speak", '
        # speak_content missing — required field
        '"reasoning": "test"}'
    )
    exc = _make_exc(body)
    assert _try_recover_missing_brace(exc, _SampleResult) is None


def test_garbage_after_closing_brace_returns_none() -> None:
    """If the body has trailing junk after the `}`, that's a different
    bug (truncation / hallucinated continuation). We don't try to fix
    everything — strict pattern match."""
    body = (
        '"selected_action": "speak", '
        '"speak_content": "ok", '
        '"reasoning": "test"} extra trailing text'
    )
    exc = _make_exc(body)
    # JSON validation will reject the trailing text; recovery returns None.
    assert _try_recover_missing_brace(exc, _SampleResult) is None
