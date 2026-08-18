"""A provider must never inherit another vendor's default model.

CIRISAgent#1062. A user selected Groq, left the model blank, and every request
failed at the provider — reported to him as an instructor retry error that named
nothing, so he was told to check an API key that was fine. His node had booted:

    'ciris_primary' started with model: gpt-4o-mini    <- base_url = api.groq.com

`OPENAI_COMPATIBLE` was mapped to "gpt-4o-mini", and the map's fallback repeated
it for every provider not listed. But OPENAI_COMPATIBLE means "speaks the OpenAI
protocol" — it is how we reach Groq, Together, DeepInfra, OpenRouter and every
local server. None of them serve gpt-4o-mini.

These tests read the resolution table directly rather than booting a runtime:
the defect was a value in a dict, and a test that mocks its way to the same
answer would pass against the bug.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
SRC = REPO / "ciris_engine" / "logic" / "runtime" / "service_initializer.py"

#: Models that belong to one vendor and must never be handed to another.
_VENDOR_MODELS = ("gpt-4o", "gpt-4", "gpt-3.5", "claude-", "gemini-")


def _default_models_map() -> dict[str, str]:
    """The `default_models` literal, read from the source."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "default_models" for t in node.targets
        ):
            out: dict[str, str] = {}
            assert isinstance(node.value, ast.Dict)
            for k, v in zip(node.value.keys, node.value.values):
                key = ast.unparse(k) if k is not None else "?"
                if isinstance(v, ast.Constant):
                    out[key] = str(v.value)
            return out
    raise AssertionError("default_models literal not found — it was renamed or removed")


def test_openai_compatible_has_no_default_model() -> None:
    """The protocol a provider speaks says nothing about its catalogue."""
    m = _default_models_map()
    offending = {k: v for k, v in m.items() if "OPENAI_COMPATIBLE" in k}
    assert not offending, (
        "OPENAI_COMPATIBLE must NOT carry a default model: it is how we reach Groq, "
        f"Together, DeepInfra, OpenRouter and local servers. Found {offending}. "
        "A wrong model fails every request at the provider and reports it as an "
        "instructor retry error, which names nothing."
    )


def test_every_default_belongs_to_the_provider_it_is_keyed_under() -> None:
    """No entry may hand one vendor's model to another."""
    m = _default_models_map()
    for provider, model in m.items():
        p = provider.upper()
        if model.startswith(("gpt-3", "gpt-4")):
            assert "OPENAI" in p and "COMPATIBLE" not in p, f"{provider} -> {model}"
        elif model.startswith("claude-"):
            assert "ANTHROPIC" in p, f"{provider} -> {model}"
        elif model.startswith("gemini-"):
            assert "GOOGLE" in p, f"{provider} -> {model}"


def test_unknown_provider_gets_no_invented_model() -> None:
    """`.get(provider, <fallback>)` must not smuggle a vendor model back in.

    This is where it actually happened: OPENAI_COMPATIBLE could have been absent
    from the map entirely and the trailing default would still have produced
    gpt-4o-mini for Groq.
    """
    src = SRC.read_text(encoding="utf-8")
    idx = src.find("default_models.get(provider")
    assert idx != -1, "the resolution call was renamed — update this test"
    call = src[idx : idx + 200]
    for vendor_model in _VENDOR_MODELS:
        assert vendor_model not in call, (
            f"the fallback for an unknown provider still yields {vendor_model!r}: {call.splitlines()[0]!r}. "
            "An unknown provider has no known catalogue; refuse instead of guessing."
        )


def test_a_provider_with_no_model_says_so_loudly() -> None:
    """Say it, but do not refuse — refusing broke local inference twice.

    Locality is derived from base_url, which is empty whenever the endpoint was
    configured by any route other than OPENAI_API_BASE, so a refusal gated on it
    fails closed on users who did nothing wrong. 2.9.24's rule holds: always keep
    one door open. The cross-vendor substitution is prevented above; this is only
    about being legible.
    """
    src = SRC.read_text(encoding="utf-8")
    assert "NO MODEL CONFIGURED for provider" in src, "the warning is gone"
    assert "CIRIS_LLM_MODEL_NAME" in src, "the message must name the way out"


def test_an_unset_model_never_becomes_an_openai_one_at_call_time() -> None:
    """The last place a Groq endpoint could still be handed gpt-4o-mini."""
    svc = (REPO / "ciris_engine/logic/services/runtime/llm_service/service.py").read_text(encoding="utf-8")
    assert 'model_name or "gpt-4o-mini"' not in svc, (
        "an unset model must stay unset — substituting an OpenAI model here "
        "reintroduces the exact failure at call time"
    )
