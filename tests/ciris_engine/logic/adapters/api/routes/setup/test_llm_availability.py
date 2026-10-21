"""Any wizard path that ends without a usable LLM must disarm the boot gate.

``llm_service`` is optional ONLY on the first run. On the next boot
``is_first_run()`` is False, so ``verify_core_services`` promotes it to critical
and initialization **aborts — it does not degrade**. So a wizard that finishes
with ``provider="OpenAI", key=""`` (the untouched default) writes a config that
boots exactly once. ``CIRIS_SERVICES_DISABLED=true`` is the existing, shipped
mechanism that keeps the service optional; these tests pin that it is written on
every such path, not only the explicit "run without AI" click.
"""

from __future__ import annotations

from io import StringIO

import pytest

from ciris_engine.logic.adapters.api.routes.setup.complete import (
    KEYLESS_LLM_PROVIDERS,
    _has_usable_llm_provider,
    _write_llm_availability_config,
)
from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest


def _request(**kwargs: object) -> SetupCompleteRequest:
    base: dict[str, object] = {
        "llm_provider": "openai",
        "llm_api_key": "sk-real-key",
        "admin_username": "owner",
    }
    base.update(kwargs)
    return SetupCompleteRequest(**base)  # type: ignore[arg-type]


def _written(setup: SetupCompleteRequest) -> str:
    f = StringIO()
    _write_llm_availability_config(f, setup)
    return f.getvalue()


class TestUsableProvider:
    def test_provider_with_a_key_is_usable(self) -> None:
        assert _has_usable_llm_provider(_request()) is True

    @pytest.mark.parametrize("provider", sorted(KEYLESS_LLM_PROVIDERS))
    def test_keyless_providers_are_usable_without_a_key(self, provider: str) -> None:
        assert _has_usable_llm_provider(_request(llm_provider=provider, llm_api_key="")) is True

    def test_the_untouched_default_is_not_usable(self) -> None:
        """provider="OpenAI", key="" — the state §3 says must never ship as-is."""
        assert _has_usable_llm_provider(_request(llm_provider="OpenAI", llm_api_key="")) is False

    def test_whitespace_is_not_a_key(self) -> None:
        assert _has_usable_llm_provider(_request(llm_api_key="   ")) is False

    def test_provider_matching_is_case_insensitive(self) -> None:
        assert _has_usable_llm_provider(_request(llm_provider="Local", llm_api_key="")) is True

    def test_explicit_none_provider_is_not_usable(self) -> None:
        assert _has_usable_llm_provider(_request(llm_provider="none", llm_api_key="")) is False

    def test_run_without_ai_overrides_a_usable_provider(self) -> None:
        """The explicit choice wins even if a key happens to be filled in."""
        assert _has_usable_llm_provider(_request(run_without_ai=True)) is False


class TestServicesDisabledFlag:
    def test_run_without_ai_writes_the_flag(self) -> None:
        assert "CIRIS_SERVICES_DISABLED=true" in _written(_request(run_without_ai=True))

    def test_no_usable_provider_writes_the_flag(self) -> None:
        """The regression guard for the abort: this path used to write nothing."""
        out = _written(_request(llm_provider="OpenAI", llm_api_key=""))
        assert "CIRIS_SERVICES_DISABLED=true" in out

    def test_usable_provider_writes_nothing(self) -> None:
        assert _written(_request()) == ""

    @pytest.mark.parametrize("provider", sorted(KEYLESS_LLM_PROVIDERS))
    def test_keyless_provider_writes_nothing(self, provider: str) -> None:
        """On-device inference is a working agent — do NOT disable services."""
        assert _written(_request(llm_provider=provider, llm_api_key="")) == ""

    def test_the_flag_is_never_written_false(self) -> None:
        """Only the disable state is expressed; absence is the enabled state."""
        assert "CIRIS_SERVICES_DISABLED=false" not in _written(_request(run_without_ai=True))


class TestDefaults:
    def test_ai_is_not_off_by_default(self) -> None:
        """§3 CRITICAL — running without AI is an option, never a default."""
        assert SetupCompleteRequest(llm_provider="openai", llm_api_key="k").run_without_ai is False

    def test_analyze_defaults_on_for_clients_that_do_not_send_it(self) -> None:
        assert SetupCompleteRequest(llm_provider="openai", llm_api_key="k").trace_analyze is True
