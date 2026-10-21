"""The mock LLM never puts prompt or message content into a result field (CIRISAgent#1244).

``extract_context_from_messages`` appends ``__messages__:<every message>`` for
the mock's own routing (action_selection reads it back). ``ds_dma`` used to
return those items as ``flags`` and join them into ``reasoning``, and that put
the whole message array, Accord system prompt included, into 766 production
traces. ``cs_dma`` did the same under inject_error, and the unstructured
fallback echoed it into content.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from ciris_adapters.mock_llm import responses
from ciris_adapters.mock_llm.responses import _RESPONSE_MAP, create_response, set_mock_config

SYSTEM_SENTINEL = "ACCORD-SYSTEM-PROMPT-SENTINEL-7f3a"
USER_SENTINEL = "USER-CONFIDENTIAL-SENTINEL-91bc"


def _messages() -> list:
    return [
        {"role": "system", "content": f"{SYSTEM_SENTINEL} You are Ally. Follow the Accord."},
        {"role": "user", "content": f"Hello there {USER_SENTINEL}"},
    ]


@pytest.fixture(params=[False, True], ids=["normal", "inject_error"])
def inject_error(request: pytest.FixtureRequest) -> Iterator[bool]:
    set_mock_config(inject_error=request.param)
    yield bool(request.param)
    set_mock_config(inject_error=False)


def _dump(result: Any) -> str:
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(mode="json"), default=str)
    return json.dumps(result, default=lambda o: getattr(o, "__dict__", str(o)))


DMA_MODELS = [
    m for m in _RESPONSE_MAP if m.__name__ in ("CSDMAResult", "DSDMAResult", "IDMAResult", "EthicalDMAResult")
]


@pytest.mark.parametrize("model", DMA_MODELS, ids=lambda m: m.__name__)
def test_no_dma_result_carries_messages_or_prompt(model: Any, inject_error: bool) -> None:
    dumped = _dump(create_response(model, messages=_messages()))
    assert responses.MESSAGES_CONTEXT_PREFIX not in dumped
    assert SYSTEM_SENTINEL not in dumped
    assert USER_SENTINEL not in dumped


@pytest.mark.parametrize("model", list(_RESPONSE_MAP), ids=lambda m: m.__name__)
def test_no_mock_result_carries_the_system_prompt(model: Any, inject_error: bool) -> None:
    """Every builder, action selection and consciences included."""
    dumped = _dump(create_response(model, messages=_messages()))
    assert responses.MESSAGES_CONTEXT_PREFIX not in dumped
    assert SYSTEM_SENTINEL not in dumped


def test_unstructured_fallback_does_not_echo_context() -> None:
    class _Unknown:
        pass

    result = create_response(_Unknown, messages=_messages())
    content = result.choices[0].message.content
    assert SYSTEM_SENTINEL not in content and responses.MESSAGES_CONTEXT_PREFIX not in content


def test_messages_still_reach_the_mocks_own_routing() -> None:
    """Internal routing keeps working: the context item is still produced."""
    context = responses.extract_context_from_messages(_messages())
    assert any(item.startswith(responses.MESSAGES_CONTEXT_PREFIX) for item in context)
