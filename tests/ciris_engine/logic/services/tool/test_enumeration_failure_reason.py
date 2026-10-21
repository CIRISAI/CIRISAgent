"""Discovery reports WHY an adapter's tools could not be listed (#945).

`_instantiate_and_check_with_info` returned `(None, None)` on any exception, so
"provides no tools", "instantiation failed", and "needs runtime collaborators"
were one indistinguishable answer. 13 adapters landed there — including
`wallet` (send_money) and `home_assistant` (device control), the two whose
tools an operator would most want disclosed.

The first-run wizard already refused to render an empty list, because an empty
list reads as "this grants nothing" — a false assurance at the moment someone
is deciding what to enable. But all it could say instead was "unavailable",
which is honest and unhelpful. These tests pin that a reason is captured and
that it reaches the disclosure.
"""

from __future__ import annotations

from typing import Any

import pytest

from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
from ciris_engine.logic.services.tool.tool_disclosure import _UNAVAILABLE_NOTE, _unavailable_note


class TestReasonCapture:
    def test_no_reason_recorded_for_an_adapter_that_enumerated_fine(self) -> None:
        assert AdapterDiscoveryService().enumeration_failure_reason("anything") is None

    def test_collaborator_requirement_is_named_as_such(self) -> None:
        """A TypeError on the no-args path means the constructor wants live
        collaborators — "enumerable after load", not "broken"."""
        svc = AdapterDiscoveryService()
        svc._record_enumeration_failure("wallet", "its tool service needs runtime collaborators")
        reason = svc.enumeration_failure_reason("wallet")
        assert reason is not None
        assert "collaborators" in reason

    def test_reasons_are_per_adapter(self) -> None:
        svc = AdapterDiscoveryService()
        svc._record_enumeration_failure("wallet", "needs collaborators")
        svc._record_enumeration_failure("mcp_client", "could not be constructed (RuntimeError: boom)")
        assert svc.enumeration_failure_reason("wallet") == "needs collaborators"
        assert svc.enumeration_failure_reason("mcp_client") != svc.enumeration_failure_reason("wallet")


class TestDisclosureNote:
    def test_specific_reason_reaches_the_operator(self) -> None:
        svc = AdapterDiscoveryService()
        svc._record_enumeration_failure("wallet", "its tool service needs runtime collaborators")
        note = _unavailable_note(svc, "wallet")
        assert "needs runtime collaborators" in note
        assert note != _UNAVAILABLE_NOTE

    def test_falls_back_rather_than_inventing_a_cause(self) -> None:
        assert _unavailable_note(AdapterDiscoveryService(), "unknown_adapter") == _UNAVAILABLE_NOTE

    def test_the_grant_warning_survives_every_branch(self) -> None:
        """The load-bearing sentence. Whatever the reason, the operator still
        needs to know that enabling this grants whatever it later registers —
        so it must not be lost when a specific reason is available."""
        svc = AdapterDiscoveryService()
        svc._record_enumeration_failure("wallet", "its tool service needs runtime collaborators")
        for note in (_unavailable_note(svc, "wallet"), _unavailable_note(svc, "absent")):
            assert "grants whatever tools it registers" in note

    def test_disclosure_never_fails_on_a_broken_discovery_object(self) -> None:
        """Defensive: the disclosure surface must degrade, not raise."""

        class Exploding:
            def enumeration_failure_reason(self, name: str) -> Any:
                raise RuntimeError("discovery is broken")

        assert _unavailable_note(Exploding(), "wallet") == _UNAVAILABLE_NOTE


class TestAgainstTheRealAdapterTree:
    @pytest.mark.asyncio
    async def test_wallet_and_home_assistant_now_report_a_reason(self) -> None:
        """The two adapters #945 names, against the real manifests in-tree.

        If either ever becomes enumerable without live collaborators — the
        item-2 fix — this test should be updated to assert that instead. It
        failing because an adapter got BETTER is a good failure.
        """
        svc = AdapterDiscoveryService()
        await svc.get_discovery_report()
        for adapter in ("wallet", "home_assistant"):
            reason = svc.enumeration_failure_reason(adapter)
            assert reason is not None, f"{adapter} still collapses to no-reason"
            assert reason.strip()
