"""The Gemini harm-category patch must land where instructor calls it (#1383).

instructor >= 1.17 moved the Gemini helpers to ``instructor.v2.providers.gemini.utils``
and left ``instructor.providers.gemini.utils`` as a re-export facade. A patch set on the
facade is never called, so the request goes out with every category instructor knows,
including ones the Gemini API rejects for some models.
"""

import pytest


def test_the_patch_replaces_the_function_instructor_calls(monkeypatch):
    pytest.importorskip("google.genai")
    from google.genai.types import HarmCategory
    from instructor.v2.providers.gemini import utils as gemini_utils

    from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

    # Restore instructor's original function after the test.
    monkeypatch.setattr(gemini_utils, "update_genai_kwargs", gemini_utils.update_genai_kwargs)

    service = object.__new__(OpenAICompatibleClient)
    service._init_google_client("test-key", "gemini-2.5-flash", 45)

    config = gemini_utils.update_genai_kwargs({"generation_config": {"max_tokens": 10}}, {})

    categories = {entry["category"] for entry in config["safety_settings"]}
    assert categories == {
        HarmCategory.HARM_CATEGORY_HARASSMENT,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    }
    assert config["max_output_tokens"] == 10
