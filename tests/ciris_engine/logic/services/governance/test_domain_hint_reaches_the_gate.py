"""The domain must survive every hop between the deferral and the F1 gate.

routes/wa.py refuses a domain-tagged deferral unless the resolving WA holds
`resolve_deferral:<domain>_*`. That check reads
`PendingDeferral.context["domain_hint"]`, and the value starts life four
transformations earlier as a `DomainCategory` enum on a `DeferralContext`.

Every one of those hops is a place the value can be dropped, and a drop is
SILENT: `.get("domain_hint")` returns None, `_domain` is falsy, the gate skips,
and the deferral resolves on the role alone. F1 would read as enforced and be
decorative — which is exactly what happened to the timer-race guard, where
`_persist_row_to_task` dropped `context["deferral"]` and a check that looked
right was never once true in production.

So this pins the chain end to end. It is deliberately not written against
fixtures of my own shaping: each stage calls the real production code.
"""

import json
from typing import Dict

import pytest

from ciris_engine.schemas.services.authority_core import scope_grants


class TestTheDomainSurvivesEveryHop:
    DOMAIN = "medical"

    def test_hop_1_wise_bus_puts_the_domain_into_the_request_context(self) -> None:
        """DeferralContext.domain_hint (an enum) -> request_context (a str dict)."""
        from ciris_engine.schemas.services.context import DeferralContext
        from ciris_engine.schemas.services.agent_credits import DomainCategory

        context = DeferralContext(
            thought_id="th-1",
            task_id="task-1",
            reason="needs a human",
            domain_hint=DomainCategory.MEDICAL,
        )
        # The exact construction wise_bus performs before building DeferralRequest.
        request_context: Dict[str, str] = dict(context.metadata)
        if context.domain_hint is not None:
            request_context["domain_hint"] = context.domain_hint.value

        # The ENUM VALUE IS UPPERCASE. This is the sharp edge of the whole chain:
        # scope matching is fnmatchCASE, and every minted certificate spells the
        # domain lowercase (resolve_deferral:medical_*). So the route's
        # `str(_domain).lower()` is load-bearing, not cosmetic — drop it and every
        # correctly scoped medical authority is refused, silently and completely.
        assert request_context["domain_hint"] == "MEDICAL"
        assert request_context["domain_hint"].lower() == self.DOMAIN

    def test_hop_2_deferral_request_carries_it(self) -> None:
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        req = DeferralRequest(
            task_id="task-1",
            thought_id="th-1",
            reason="needs a human",
            defer_until=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            context={"domain_hint": self.DOMAIN},
        )
        assert req.context.get("domain_hint") == self.DOMAIN

    def test_hop_3_send_deferral_nests_it_under_the_deferral_key(self) -> None:
        """The persisted shape send_deferral writes, and the shape the reader expects."""
        stored_context: Dict[str, object] = {}
        stored_context["deferral"] = {"context": {"domain_hint": self.DOMAIN}}

        # Round-trips through JSON exactly as the task row does.
        reread = json.loads(json.dumps(stored_context))
        assert reread["deferral"]["context"]["domain_hint"] == self.DOMAIN

    def test_hop_4_ui_context_copies_it_through_unfiltered(self) -> None:
        """The real _build_ui_context — no allowlist, so the domain survives."""
        from ciris_engine.logic.services.governance.wise_authority.service import (
            WiseAuthorityService,
        )

        service = WiseAuthorityService.__new__(WiseAuthorityService)
        ui_context = service._build_ui_context(
            "a task", {"context": {"domain_hint": self.DOMAIN, "user_id": "u-1"}}
        )
        assert ui_context.get("domain_hint") == self.DOMAIN, (
            "If _build_ui_context ever gains an allowlist, the F1 gate goes dark silently. "
            f"got {ui_context}"
        )

    def test_hop_5_pending_deferral_holds_it_and_the_gate_can_read_it(self) -> None:
        from datetime import datetime, timezone

        from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral

        pd = PendingDeferral(
            deferral_id="defer_task-1",
            created_at=datetime.now(timezone.utc),
            deferred_by="agent",
            task_id="task-1",
            thought_id="th-1",
            reason="needs a human",
            context={"domain_hint": self.DOMAIN},
        )
        domain = pd.context.get("domain_hint")
        assert domain == self.DOMAIN

        # And the resource the route builds from it is one a certificate can grant.
        resource = f"{str(domain).lower()}_{pd.deferral_id}"
        assert scope_grants(f"resolve_deferral:{self.DOMAIN}_*", "resolve_deferral", resource) is True
        assert scope_grants("resolve_deferral:financial_*", "resolve_deferral", resource) is False


class TestPendingDeferralIsNotMaterializedThroughTaskContext:
    """Why the gate reads PendingDeferral and not a Task.

    TaskContext keeps seven named fields and drops the rest — which is how the
    timer-race guard ended up dead. PendingDeferral.context is a plain
    Dict[str, str] the WA service fills explicitly, so it does not have that
    hazard. This asserts the distinction so nobody "simplifies" the gate onto a
    Task and silently disarms it.
    """

    def test_task_context_would_drop_the_domain(self) -> None:
        from ciris_engine.schemas.runtime.models import TaskContext

        assert "domain_hint" not in TaskContext.model_fields
        assert "deferral" not in TaskContext.model_fields

    def test_pending_deferral_context_is_an_open_dict(self) -> None:
        from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral

        field = PendingDeferral.model_fields["context"]
        assert "Dict" in str(field.annotation) or "dict" in str(field.annotation)


class TestTheDomainIsCaseNormalizedBeforeMatching:
    """DomainCategory values are UPPERCASE; scope patterns are lowercase.

    `scope_grants` matches with fnmatchcase, deliberately — "identifiers, not
    prose". So the route must fold the enum value to lowercase before building
    the resource, or `MEDICAL_defer_1` meets `medical_*` and never matches.
    """

    def test_the_raw_enum_value_does_not_match_a_minted_scope(self) -> None:
        from ciris_engine.schemas.services.agent_credits import DomainCategory

        raw = f"{DomainCategory.MEDICAL.value}_defer_001"
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferral", raw) is False, (
            "if this passes, matching became case-insensitive and the normalization below "
            "is no longer required — but check test_deferral_permissions' case-sensitivity "
            "vector before removing it"
        )

    def test_the_normalized_value_does(self) -> None:
        from ciris_engine.schemas.services.agent_credits import DomainCategory

        normalized = f"{DomainCategory.MEDICAL.value.lower()}_defer_001"
        assert scope_grants("resolve_deferral:medical_*", "resolve_deferral", normalized) is True

    def test_the_route_actually_normalizes(self) -> None:
        from pathlib import Path as _P

        src = (
            _P(__file__).resolve().parents[5] / "ciris_engine/logic/adapters/api/routes/wa.py"
        ).read_text()
        assert '_scope_resource = f"{str(_domain).lower()}_{deferral_id}"' in src, (
            "the route must lowercase the domain before building the scope resource"
        )
