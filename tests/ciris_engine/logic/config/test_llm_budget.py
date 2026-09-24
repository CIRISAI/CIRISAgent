"""The one local-vs-remote decision and the budget profiles (CIRISAgent#1186)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.logic.config.llm_budget import Deadline, classify_provider, resolve_budget
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE, REMOTE_PROFILE, LLMBudgetProfile, ProviderClass

L, R = ProviderClass.LOCAL, ProviderClass.REMOTE


@pytest.fixture
def env(monkeypatch):
    """Isolate get_env_var from the host's .env and os.environ."""
    table: dict[str, str] = {}
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: table.get(name, default))
    return table


class TestClassifier:
    @pytest.mark.parametrize(
        "url,expected",
        [
            # The four sites used to disagree on every one of these (#1186 part 2).
            ("http://jetson.local:11434/v1", L),
            ("http://localhost:11434/v1", L),
            ("http://127.0.0.1:8080/v1", L),
            ("http://[::1]:8080/v1", L),
            ("http://192.168.1.20:11434/v1", L),
            ("http://10.4.2.9:8000/v1", L),
            ("http://172.20.0.5:11434/v1", L),  # all of 172.16/12, not only 172.16.x
            ("http://100.101.102.103:11434/v1", L),  # Tailscale / CGNAT
            ("http://gpu-box:11434/v1", L),  # bare LAN hostname on a local-server port
            ("https://openrouter.ai/api/v1", R),
            ("https://api.together.xyz/v1", R),
            ("https://api.deepinfra.com/v1/openai", R),
            ("https://api.groq.com/openai/v1", R),
            ("https://api.v10.example.com/v1", R),  # "10." as a substring is not a private IP
            ("https://llm.example.com:8080/v1", R),  # a public host on a common port is still public
            ("https://proxy.ciris.ai/v1", R),
        ],
    )
    def test_url(self, url, expected):
        assert classify_provider(None, url) is expected

    @pytest.mark.parametrize("pid", ["local", "local_inference", "mobile_local", "LOCAL", " localai "])
    def test_declared_local_wins_over_any_url(self, pid):
        assert classify_provider(pid, "https://some-tunnel.example.com/v1") is L

    def test_no_url_no_declaration_is_a_hosted_sdk_default(self):
        assert classify_provider(None, None) is R
        assert classify_provider("anthropic", None) is R


class TestProfiles:
    def test_remote_values_are_the_measured_ones(self):
        assert (REMOTE_PROFILE.conscience_per_try_s, REMOTE_PROFILE.conscience_attempts) == (45.0, 4)
        assert REMOTE_PROFILE.interact_deadline_s == 195.0

    def test_local_is_one_long_try(self):
        assert LOCAL_PROFILE.conscience_attempts == 1 and LOCAL_PROFILE.dma_attempts == 1
        assert LOCAL_PROFILE.conscience_per_try_s >= 4 * REMOTE_PROFILE.conscience_per_try_s

    @pytest.mark.parametrize("p", [REMOTE_PROFILE, LOCAL_PROFILE])
    def test_nesting(self, p):
        assert p.llm_http_timeout_s <= p.conscience_per_try_s
        assert p.llm_http_timeout_s <= p.dma_per_try_s
        assert p.thought_budget_s <= p.interact_deadline_s

    def test_a_profile_whose_inner_timeout_outlives_the_outer_is_rejected(self):
        with pytest.raises(ValidationError, match="never report its own timeout"):
            REMOTE_PROFILE.model_validate({**REMOTE_PROFILE.model_dump(), "llm_http_timeout_s": 60.0})


class TestResolve:
    def test_profile_follows_the_provider(self, env):
        assert resolve_budget("local", None) == LOCAL_PROFILE
        assert resolve_budget(None, "https://openrouter.ai/api/v1") == REMOTE_PROFILE

    def test_forced_profile_wins(self, env):
        env["CIRIS_LLM_BUDGET_PROFILE"] = "local"
        assert resolve_budget(None, "https://openrouter.ai/api/v1").provider_class is L

    def test_env_overrides_each_knob(self, env):
        env.update(
            {
                "CIRIS_CONSCIENCE_TIMEOUT": "50",
                "CIRIS_CONSCIENCE_ATTEMPTS": "3",
                "CIRIS_DMA_ATTEMPTS": "1",
                "CIRIS_API_INTERACTION_TIMEOUT": "300",
                "CIRIS_THOUGHT_BUDGET": "280",
            }
        )
        b = resolve_budget(None, "https://openrouter.ai/api/v1")
        assert (b.conscience_per_try_s, b.conscience_attempts, b.dma_attempts) == (50.0, 3, 1)
        assert (b.interact_deadline_s, b.thought_budget_s) == (300.0, 280.0)

    def test_a_long_http_override_raises_the_per_try_instead_of_breaking_boot(self, env):
        env["CIRIS_LLM_TIMEOUT"] = "120"
        b = resolve_budget(None, "https://openrouter.ai/api/v1")
        assert b.llm_http_timeout_s == 120 and b.conscience_per_try_s >= 120 and b.dma_per_try_s >= 120
        LLMBudgetProfile.model_validate(b.model_dump())  # still a valid profile

    def test_a_short_interact_override_caps_the_thought_budget(self, env):
        env["CIRIS_API_INTERACTION_TIMEOUT"] = "110"
        assert resolve_budget(None, None).thought_budget_s == 110

    @pytest.mark.parametrize("bad", ["abc", "-5", "0"])
    def test_garbage_overrides_fall_back(self, env, bad):
        env["CIRIS_CONSCIENCE_TIMEOUT"] = bad
        env["CIRIS_CONSCIENCE_ATTEMPTS"] = bad
        b = resolve_budget(None, None)
        assert (b.conscience_per_try_s, b.conscience_attempts) == (45.0, 4)

    def test_active_budget_reads_the_declared_provider(self, env):
        env.update({"LLM_PROVIDER": "local", "OPENAI_API_BASE": "https://tunnel.example.com/v1"})
        assert lb.active_budget().provider_class is L


class TestDeadline:
    def test_remainder_and_clamp(self):
        now = [100.0]
        d = Deadline(60.0, clock=lambda: now[0])
        assert d.clamp(45.0) == 45.0
        now[0] = 130.0
        assert d.remaining() == 30.0 and d.clamp(45.0) == 30.0
        assert d.affords(20.0) and not d.affords(31.0)
        now[0] = 200.0
        assert d.expired() and d.remaining() == 0.0 and d.clamp(45.0) == 0.0
