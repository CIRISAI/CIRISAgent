"""Code admission (rc21 CC 2.7.11, `admission:unit`) for units beyond the attested build."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.infrastructure.authorization import unit_admission as ua
from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
from ciris_engine.schemas.adapters.tools import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
)
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState
from ciris_engine.schemas.runtime.unit_admission import (
    UNIT_LEASE_MAX_SECS,
    AdmissionRead,
    AdmissionSigner,
    UnitAdmissionRow,
    UnitAdmissionToken,
    UnitCapability,
)

OWNER = "pytest-stub-owner"  # the conftest owner-binding stub's owner key
AGENT_KEY = "agent-signing-key"
NOW = 1_800_000_000_000
C = UnitCapability


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    ua._reset_for_tests()
    monkeypatch.setattr(ua, "_program_key_ids", lambda: {AGENT_KEY, "node-key"})


def person(key: str) -> AdmissionSigner:
    return AdmissionSigner(key_id=key, identity_type="user")


def authored(author: AdmissionSigner, caps: List[str], *, sub: str = "", standing: bool = True, **kw: Any) -> UnitAdmissionRow:
    return UnitAdmissionRow(
        row_id=kw.pop("row_id", uuid.uuid4().hex),
        sub=sub,
        author=author,
        capabilities=caps,
        asserted_at_ms=kw.pop("asserted_at_ms", NOW - 1000),
        valid_until_ms=kw.pop("valid_until_ms", NOW + 3_600_000),
        standing=standing,
        **kw,
    )


def counted(voices: List[AdmissionSigner], caps: List[str], *, sub: str = "", count_met: bool = True) -> UnitAdmissionRow:
    return UnitAdmissionRow(
        row_id=uuid.uuid4().hex,
        sub=sub,
        refs_head="head-1",
        voices=voices,
        count_met=count_met,
        capabilities=caps,
        asserted_at_ms=NOW - 1000,
        valid_until_ms=NOW + 3_600_000,
        standing=True,
    )


def judge(*rows: UnitAdmissionRow, owner: Optional[str] = OWNER, now: int = NOW) -> Any:
    return ua.evaluate_admission(
        "", AdmissionRead(supported=True, rows=list(rows)), owner_key_id=owner, now_ms=now, program_keys={AGENT_KEY}
    )


def write_unit(root: Path, name: str, extra: str = "") -> Path:
    """A minimal tool adapter outside the installed package (what skill_import writes to ~/ciris/adapters)."""
    unit = root / name
    unit.mkdir(parents=True)
    (unit / "manifest.json").write_text(
        json.dumps(
            {
                "module": {"name": name, "version": "1.0.0", "description": "t", "author": "t"},
                "services": [{"type": "TOOL", "class": f"{name}.service.UnitToolService"}],
            }
        )
    )
    (unit / "__init__.py").write_text("")
    (unit / "service.py").write_text(f"class UnitToolService:\n    MARK = {extra!r}\n")
    return unit


def discover(root: Path, name: str) -> Any:
    svc = AdapterDiscoveryService(extra_paths=[root])
    manifest = next(m for m in svc.discover_adapters() if m.module.name == name)
    return svc, manifest


# ---------------------------------------------------------------------------
# Scope: the attested build is out; everything beyond it is in
# ---------------------------------------------------------------------------


class TestScope:
    def test_built_in_adapter_loads_without_a_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def no_read(*_a: Any) -> AdmissionRead:
            raise AssertionError("a built-in unit must not be read for admission")

        monkeypatch.setattr(ua, "read_admission_rows", no_read)
        bundled = AdapterDiscoveryService.BUNDLED_ROOT / "sample_adapter"
        assert not ua.is_beyond_build(bundled)
        assert ua.check_unit_load_sync(bundled, "sample_adapter") is None

        svc = AdapterDiscoveryService()
        manifest = next(m for m in svc.discover_adapters() if m.module.name == "sample_adapter")
        cls = svc.load_service_class(manifest, manifest.services[0].class_path)
        assert cls is not None
        assert getattr(cls, ua.UNIT_RECORD_ATTR, None) is None

    def test_imported_skill_without_a_row_is_refused_before_import(self, tmp_path: Path) -> None:
        name = f"skill_{uuid.uuid4().hex[:8]}"
        write_unit(tmp_path, name)
        svc, manifest = discover(tmp_path, name)
        assert svc.load_service_class(manifest, manifest.services[0].class_path) is None
        assert f"{name}.service" not in sys.modules
        assert "admission_none:no_row" in (svc.enumeration_failure_reason(name) or "")

    @pytest.mark.asyncio
    async def test_skill_route_refuses_to_auto_load_without_a_row(self, tmp_path: Path) -> None:
        from ciris_engine.logic.adapters.api.routes.system.skill_import import unit_admission_refusal

        unit = write_unit(tmp_path, f"skill_{uuid.uuid4().hex[:8]}")
        refusal = await unit_admission_refusal(unit, unit.name)
        assert refusal is not None and refusal.startswith("admission_none:no_row")

    def test_no_substrate_support_fails_closed_with_incident_and_notice(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        unit = write_unit(tmp_path, f"skill_{uuid.uuid4().hex[:8]}")
        with caplog.at_level(logging.ERROR):
            decision = ua.check_unit_load_sync(unit, unit.name)
        assert decision is not None and decision.message() == "admission_none:no_row"
        assert decision.operator_notice == ua.OPERATOR_NOTICE_NO_SUPPORT
        assert any("UNIT ADMISSION REFUSED" in r.message for r in caplog.records)

    def test_digest_tracks_the_bytes(self, tmp_path: Path) -> None:
        a = write_unit(tmp_path / "a", "u", extra="1")
        b = write_unit(tmp_path / "b", "u", extra="2")
        c = write_unit(tmp_path / "c", "u", extra="1")
        assert ua.unit_digest(a) != ua.unit_digest(b)
        assert ua.unit_digest(a) == ua.unit_digest(c)
        assert ua.digest_tag(ua.unit_digest(a)).startswith("canonical:sha256:")


# ---------------------------------------------------------------------------
# Who may admit
# ---------------------------------------------------------------------------


class TestSigners:
    def test_owner_alone_admits_an_effect_unit_on_this_host(self) -> None:
        d = judge(authored(person(OWNER), ["compute", "net_send"], standing=False))
        assert d.admitted and set(d.admitted_capabilities) == {C.COMPUTE, C.NET_SEND}

    def test_owner_alone_row_admits_nothing_on_another_host(self) -> None:
        d = judge(authored(person(OWNER), ["net_send"]), owner="someone-else")
        assert d.token == UnitAdmissionToken.ISSUER_NOT_REACHED

    def test_owner_alone_loads_an_effect_unit_end_to_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        name = f"skill_{uuid.uuid4().hex[:8]}"
        unit = write_unit(tmp_path, name)
        sub = ua.digest_tag(ua.unit_digest(unit))
        monkeypatch.setattr(ua, "_host_owner_key_sync", lambda: OWNER)
        monkeypatch.setattr(
            ua,
            "read_admission_rows",
            lambda s, o: AdmissionRead(
                supported=True, rows=[authored(person(OWNER), ["net_send"], sub=sub, asserted_at_ms=ua._now_ms() - 1000, valid_until_ms=ua._now_ms() + 60_000)]
            ),
        )
        svc, manifest = discover(tmp_path, name)
        cls = svc.load_service_class(manifest, manifest.services[0].class_path)
        assert cls is not None
        record = getattr(cls, ua.UNIT_RECORD_ATTR)
        assert record.digest == sub

    def test_non_owner_single_person_is_refused_for_effects(self) -> None:
        # Authored by a person who stands here but does not own the host.
        assert judge(authored(person("alice"), ["net_send"])).token == UnitAdmissionToken.ISSUER_NOT_REACHED
        # Counted, but only one person: held, never admitted.
        d = judge(counted([person("alice")], ["net_send"]))
        assert d.token == UnitAdmissionToken.COUNT_UNMET
        # Two persons and the protocol met: admitted.
        assert judge(counted([person("alice"), person("bob")], ["net_send"])).admitted
        # Protocol not met at the head: held.
        assert judge(counted([person("alice"), person("bob")], ["net_send"], count_met=False)).token == (
            UnitAdmissionToken.COUNT_UNMET
        )

    def test_non_owner_person_may_admit_compute_alone_where_they_stand(self) -> None:
        assert judge(authored(person("alice"), ["compute", "read"])).admitted
        assert judge(authored(person("alice"), ["compute"], standing=False)).token == UnitAdmissionToken.ISSUER_NOT_REACHED

    def test_agents_own_key_cannot_admit(self) -> None:
        # Even typed as a person, and even named as the owner, the agent's own key admits nothing.
        lying = AdmissionSigner(key_id=AGENT_KEY, identity_type="user")
        assert judge(authored(lying, ["compute"]), owner=AGENT_KEY).token == UnitAdmissionToken.ISSUER_NOT_PERSON
        for kind in ("agent", "node", "node,agent", "user,agent"):
            prog = AdmissionSigner(key_id="k", identity_type=kind)
            assert judge(authored(prog, ["compute"]), owner="k").token == UnitAdmissionToken.ISSUER_NOT_PERSON
        # As a voice it is refused alone, so one person plus the agent is no count.
        d = judge(counted([person("alice"), AdmissionSigner(key_id=AGENT_KEY, identity_type="agent")], ["net_send"]))
        assert d.token == UnitAdmissionToken.COUNT_UNMET

    def test_program_keys_include_the_agents_signing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.undo()
        from ciris_engine.logic.persistence.models import graph

        class Engine:
            def local_derived_key_id(self) -> str:
                return "the-agent-key"

        monkeypatch.setattr(graph, "get_persist_engine", lambda: Engine())
        assert "the-agent-key" in ua._program_key_ids()
        lying = AdmissionSigner(key_id="the-agent-key", identity_type="accord_holder")
        d = ua.evaluate_admission(
            "", AdmissionRead(supported=True, rows=[authored(lying, ["compute"])]), owner_key_id="the-agent-key", now_ms=NOW
        )
        assert d.token == UnitAdmissionToken.ISSUER_NOT_PERSON


# ---------------------------------------------------------------------------
# The lease and the end
# ---------------------------------------------------------------------------


class TestLease:
    def test_lease_expiry(self) -> None:
        row = authored(person(OWNER), ["compute"], asserted_at_ms=NOW - 10_000, valid_until_ms=NOW)
        d = judge(row)
        assert d.message() == "admission_none:lease_ended"
        assert judge(authored(person(OWNER), ["compute"], asserted_at_ms=NOW - 10_000, valid_until_ms=NOW + 1)).admitted

    def test_lease_ends_a_day_after_first_held(self) -> None:
        hour = 3_600_000
        # Held ten hours before its lease opens; the lease still ends a day after the host first held it.
        row = authored(person(OWNER), ["compute"], asserted_at_ms=NOW, valid_until_ms=NOW + 24 * hour)
        assert judge(row, now=NOW - 10 * hour).message() == "admission_none:no_row"
        assert judge(row, now=NOW + 13 * hour).admitted
        assert judge(row, now=NOW + 15 * hour).message() == "admission_none:lease_ended"

    def test_lease_longer_than_a_day_admits_nothing(self) -> None:
        row = authored(person(OWNER), ["compute"], asserted_at_ms=NOW - 1000, valid_until_ms=NOW - 1000 + UNIT_LEASE_MAX_SECS * 1000 + 1)
        assert judge(row).message() == "admission_none:no_row"

    def test_withdrawn_and_unknown_capability(self) -> None:
        assert judge(authored(person(OWNER), ["compute"], withdrawn=True)).message() == "admission_none:withdrawn"
        assert judge(authored(person(OWNER), ["teleport"])).message() == "admission_none:no_row"

    def test_renewal_unions_live_rows(self) -> None:
        d = judge(
            authored(person(OWNER), ["compute"]),
            authored(person(OWNER), ["store_write"]),
            authored(person(OWNER), ["actuate"], valid_until_ms=NOW),
        )
        assert set(d.admitted_capabilities) == {C.COMPUTE, C.STORE_WRITE}


# ---------------------------------------------------------------------------
# Effects: capability, attenuation, halt
# ---------------------------------------------------------------------------


class Svc:
    def __init__(self, caps: Optional[List[UnitCapability]]) -> None:
        self.caps = caps
        self.calls = 0

    async def get_available_tools(self) -> List[str]:
        return ["t"]

    async def get_tool_info(self, name: str) -> ToolInfo:
        return ToolInfo(name=name, description="t", parameters=ToolParameterSchema(type="object", properties={}), unit_capabilities=self.caps)

    async def execute_tool(self, name: str, params: Dict[str, Any]) -> ToolExecutionResult:
        self.calls += 1
        return ToolExecutionResult(tool_name=name, status=ToolExecutionStatus.COMPLETED, success=True, data=None, error=None, correlation_id="c")


def unit_service(
    monkeypatch: pytest.MonkeyPatch,
    tool_caps: Optional[List[UnitCapability]],
    admitted: List[str],
    *,
    parent_held: Optional[frozenset] = None,
) -> Svc:
    cls = type(f"S{uuid.uuid4().hex[:6]}", (Svc,), {})
    sub = "canonical:sha256:" + "ab" * 32
    ua.tag_unit_class(cls, ua.UnitRecord(name="u", unit_dir="/x", digest=sub, declared=None, parent_held=parent_held))
    now = ua._now_ms()
    row = authored(person(OWNER), admitted, sub=sub, asserted_at_ms=now - 1000, valid_until_ms=now + 60_000)
    monkeypatch.setattr(ua, "read_admission_rows", lambda s, o: AdmissionRead(supported=True, rows=[row]))
    return cls(tool_caps)  # type: ignore[no-any-return]


def halt(monkeypatch: pytest.MonkeyPatch, halted: bool) -> None:
    from ciris_engine.logic.utils import halt_latch

    async def read(*, fresh: bool = False) -> AccordHaltState:
        return AccordHaltState(
            halted=halted,
            reading=AccordHaltReading.IN_EFFECT if halted else AccordHaltReading.NOT_HALTED,
            read_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(halt_latch, "read_halt_latch", read)


class TestEffects:
    @pytest.mark.asyncio
    async def test_capability_not_admitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = unit_service(monkeypatch, [C.NET_SEND], ["compute"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.message() == "admission_capability_not_admitted:net_send"

    @pytest.mark.asyncio
    async def test_undeclared_tool_needs_every_effect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = unit_service(monkeypatch, None, ["compute", "net_send"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.token == UnitAdmissionToken.CAPABILITY_NOT_ADMITTED
        svc = unit_service(monkeypatch, None, ["net_send", "submit", "sign", "store_write", "actuate"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.admitted

    @pytest.mark.asyncio
    async def test_attenuation_child_within_parent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = unit_service(monkeypatch, [C.STORE_WRITE], ["compute", "store_write"], parent_held=frozenset({C.COMPUTE}))
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.message() == "admission_capability_not_held:store_write"
        # Started inside a running unit's scope: the same rule, from the running unit.
        svc = unit_service(monkeypatch, [C.STORE_WRITE], ["compute", "store_write"])
        with ua.unit_scope(frozenset({C.COMPUTE})):
            d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.token == UnitAdmissionToken.CAPABILITY_NOT_HELD
        with ua.unit_scope(frozenset({C.COMPUTE, C.STORE_WRITE})):
            d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.admitted

    @pytest.mark.asyncio
    async def test_halt_blocks_effects_not_compute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        halt(monkeypatch, True)
        svc = unit_service(monkeypatch, [C.NET_SEND], ["compute", "read", "net_send"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.message() == "admission_halted:net_send"
        svc = unit_service(monkeypatch, [C.COMPUTE, C.READ], ["compute", "read", "net_send"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.admitted
        halt(monkeypatch, False)
        svc = unit_service(monkeypatch, [C.NET_SEND], ["compute", "read", "net_send"])
        d = await ua.check_unit_tool_call(svc, "t")
        assert d is not None and d.admitted

    @pytest.mark.asyncio
    async def test_built_in_service_is_not_a_unit(self) -> None:
        assert await ua.check_unit_tool_call(Svc(None), "t") is None

    @pytest.mark.asyncio
    async def test_tool_bus_refuses_an_unadmitted_unit_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ciris_engine.logic.buses.tool_bus import ToolBus

        svc = unit_service(monkeypatch, [C.ACTUATE], ["compute"])

        class Registry:
            _services: Dict[Any, Any] = {}

        class Clock:
            def now(self) -> datetime:
                return datetime.now(timezone.utc)

            def timestamp(self) -> float:
                return time.time()

        bus = ToolBus(service_registry=Registry(), time_service=Clock())  # type: ignore[arg-type]
        result = await bus.dispatch_to_provider(svc, "t", {})
        assert result.status == ToolExecutionStatus.UNAUTHORIZED
        assert result.error == "admission_capability_not_admitted:actuate"
        assert svc.calls == 0
