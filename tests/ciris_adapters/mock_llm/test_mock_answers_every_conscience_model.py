"""The mock LLM must answer every schema the conscience shards actually request.

It only answered the post-evaluation EntropyCheckResult / CoherenceCheckResult
wrappers, while the shards request the raw EntropyResult / CoherenceResult. So
every entropy and coherence call in mock mode fell through to the generic reply
and the shards passed on preset scores: under the mock those checks never ran.
Failing them closed (#1186) turned that into every action pondering in QA.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import ciris_engine.logic.conscience.core as conscience_core
from ciris_adapters.mock_llm.responses import _RESPONSE_MAP, create_response

# A requested model is a class passed by name (``response_model=EntropyResult,``).
# ``response_model=response_model.__name__`` (a trace field naming whichever
# model a helper was handed) is not a request and must not be collected.
_REQUESTED = sorted(set(re.findall(r"response_model=([A-Z]\w*)\s*[,)]", Path(conscience_core.__file__).read_text())))


def test_the_shards_request_something():
    assert {"EntropyResult", "CoherenceResult"} <= set(_REQUESTED), _REQUESTED


@pytest.mark.parametrize("model_name", _REQUESTED)
def test_mock_answers_with_the_requested_model(model_name):
    model = getattr(conscience_core, model_name)
    assert model in _RESPONSE_MAP, f"mock LLM has no handler for {model_name}; the shard would judge on nothing"
    assert isinstance(create_response(model, messages=[]), model)
