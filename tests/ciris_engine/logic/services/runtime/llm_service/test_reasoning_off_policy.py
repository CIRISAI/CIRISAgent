"""Reasoning is turned OFF on every provider we support, as hard as that
provider allows.

Model reasoning costs us twice: it is the difference between a 3s answer and a
60s one, and it confounds the pipeline — CIRIS does its reasoning in the DMA
chain, so a model that reasons on its own is a second, unaudited reasoner whose
output we neither see nor grade.

So the rule is not "disable it where convenient". It is: every (provider,
reasoning-model) pair sends the strongest suppression that provider accepts,
and any pair that sends nothing must be here, named, with the measurement that
justifies it.

Every value below was measured live against the provider, not read off a doc —
the docs were wrong twice (Groq has no `none`; gpt-5 rejects `minimal`).
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

OPENROUTER = "https://openrouter.ai/api/v1"
GROQ = "https://api.groq.com/openai/v1"
GOOGLE = "https://generativelanguage.googleapis.com/v1beta/openai/"
TOGETHER = "https://api.together.xyz/v1"
DEEPINFRA = "https://api.deepinfra.com/v1/openai"


def extras(base: str, model: str) -> dict:
    return OpenAICompatibleClient._build_reasoning_off_extras(base, model)


class TestEveryReasoningModelIsSuppressed:
    """The rule, pair by pair. A new provider that sends nothing fails here."""

    @pytest.mark.parametrize(
        "base,model,expected",
        [
            # OpenAI. gpt-5.2 + "minimal" is a 400: `Supported values are:
            # 'none'...`. "none" measured 0 reasoning tokens / 563ms.
            ("", "gpt-5.2", {"reasoning_effort": "none"}),
            ("https://api.openai.com/v1", "gpt-5.2", {"reasoning_effort": "none"}),
            # o-series enum is low|medium|high — "low" is its floor.
            ("", "o3-mini", {"reasoning_effort": "low"}),
            # OpenRouter's documented switch. Live: 100 tokens/4.1s -> 0/1.5s.
            (OPENROUTER, "qwen/qwen3-32b", {"reasoning": {"enabled": False}}),
            # R1 answers `400 Reasoning is mandatory for this endpoint`, so
            # asking it to stop breaks every call; ask it to be quiet instead.
            (OPENROUTER, "deepseek/deepseek-r1", {"reasoning": {"exclude": True}}),
            # Groq: "none" is a 400 (`must be one of low, medium, or high`);
            # "low" measured 103 reasoning tokens -> 11.
            (GROQ, "openai/gpt-oss-20b", {"reasoning_effort": "low"}),
            # Gemini 2.5 takes the OpenAI-surface switch.
            (GOOGLE, "gemini-2.5-flash", {"reasoning_effort": "none"}),
            # vLLM-served families.
            (DEEPINFRA, "Qwen/Qwen3.6-35B-A3B", {"chat_template_kwargs": {"enable_thinking": False}, "reasoning": {"enabled": False}}),
        ],
    )
    def test_pair_sends_its_strongest_accepted_suppression(self, base, model, expected):
        assert extras(base, model) == expected

    def test_together_layers_both_families(self):
        # Kimi honours `thinking.type`; the vLLM-served models honour
        # `chat_template_kwargs`. Each ignores the other's key, so both ship.
        got = extras(TOGETHER, "Qwen/Qwen3-235B-A22B-fp8-tput")
        assert got["thinking"] == {"type": "disabled"}
        assert got["chat_template_kwargs"] == {"enable_thinking": False}


class TestTheDocumentedExceptions:
    """Pairs that send nothing. Each needs a reason, not an omission."""

    def test_non_reasoning_models_send_nothing(self):
        # These 400 on the field itself, so sending it would break them.
        assert extras("", "gpt-4o") == {}
        assert extras(GROQ, "meta-llama/llama-4-scout") == {}

    def test_gemini_3_cannot_be_quieted_at_all(self):
        # Measured: `reasoning_effort` -> 400 INVALID_ARGUMENT, and the
        # `google.thinking_config` nesting -> 400 `Unknown name "google"` on the
        # OpenAI-compat path. Nothing is accepted, so nothing is sent.
        assert extras(GOOGLE, "gemini-3.6-flash") == {}

    def test_anthropic_reasoning_is_opt_in_so_there_is_nothing_to_disable(self):
        assert extras("https://api.anthropic.com/v1", "claude-haiku-4-5-20251001") == {}


class TestTheRegressionsThatCostUs:
    def test_empty_base_url_is_openai_not_unknown(self):
        # The SDK defaults to api.openai.com when no base_url is given — the
        # commonest config there is. It used to fall through to the
        # unknown-endpoint default and suppress nothing.
        assert extras("", "gpt-5.2") != {}

    def test_openrouter_never_gets_the_vllm_key(self):
        # OpenRouter does not document chat_template_kwargs, and sending it
        # alongside the real switch measurably UN-disabled reasoning:
        # 0 tokens/1.5s became 229 tokens/7.3s on the same model.
        assert "chat_template_kwargs" not in extras(OPENROUTER, "qwen/qwen3-32b")

    def test_groq_never_gets_reasoning_effort_none(self):
        # Groq's enum has no "none" — it is a 400, i.e. every call fails.
        assert extras(GROQ, "openai/gpt-oss-20b").get("reasoning_effort") != "none"


class TestProviderDispatchCannotBeSpoofed:
    """The endpoint is identified by its HOST, not by a substring of its URL.

    A substring test (`"api.openai.com" in base_url`) is satisfied by a
    lookalike host and by any URL that merely mentions the name in a path or
    query — CodeQL's incomplete-url-substring-sanitization, flagged high. The
    blast radius here is which reasoning payload a hostile base_url can steer
    us into sending, which is small; the fix is cheap and the class of bug is
    not one to keep.
    """

    @pytest.mark.parametrize(
        "hostile",
        [
            "https://api.openai.com.attacker.example/v1",
            "https://openrouter.ai.attacker.example/v1",
            "https://evil.example/?upstream=api.openai.com",
            "https://evil.example/proxy/openrouter.ai/v1",
            "https://notgroq.com/openai/v1",
        ],
    )
    def test_a_lookalike_host_is_not_that_provider(self, hostile):
        assert extras(hostile, "gpt-5.2") == {}

    @pytest.mark.parametrize(
        "genuine,model,key",
        [
            ("https://api.openai.com/v1", "gpt-5.2", "reasoning_effort"),
            ("https://openrouter.ai/api/v1", "qwen/qwen3-32b", "reasoning"),
            ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "reasoning_effort"),
            ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash", "reasoning_effort"),
            ("https://api.together.xyz/v1", "Qwen/Qwen3-235B", "chat_template_kwargs"),
            ("https://api.deepinfra.com/v1/openai", "Qwen/Qwen3.6-35B", "chat_template_kwargs"),
        ],
    )
    def test_the_real_endpoints_still_dispatch(self, genuine, model, key):
        assert key in extras(genuine, model)

    def test_a_regional_subdomain_still_resolves(self):
        # Subdomains of a provider ARE that provider — eu.api.openai.com must
        # not fall through to the unknown-endpoint branch and lose the switch.
        assert extras("https://eu.api.openai.com/v1", "gpt-5.2") == {"reasoning_effort": "none"}
