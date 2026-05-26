"""AIR (Artificial Interaction Reminder) QA tests.

Tests the parasocial-attachment-prevention system. AIR's reminder logic is
pure and deterministic (objective time / message-count thresholds, no I/O),
so the bulk of coverage runs IN-PROCESS against ArtificialInteractionReminder
directly — fast, exact, and reliable.

This replaces the previous HTTP-only suite, which made 9 synchronous
`/v1/agent/interact` calls (~55s each → ~8 min) and asserted nothing real:
its checks (`status == 200`, `"response" in data`) were satisfied by the
endpoint's "Still processing" timeout body, so it passed without ever
exercising AIR. The real threshold behaviour (a reminder firing at the
20-message mark) was explicitly skipped as "too long" — in-process it is
instant and is now actually tested.

One end-to-end test verifies AIR is wired into `/v1/agent/interact` and
FAILS LOUDLY if the endpoint stalls, instead of hollow-passing on a timeout.

See FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md for design rationale.
"""

import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
from rich.console import Console

logger = logging.getLogger(__name__)


class _FakeClock:
    """Controllable time source so time-threshold / idle-reset tests are
    deterministic and instant (no real waiting)."""

    def __init__(self, start: datetime = None) -> None:
        self._t = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._t

    def advance(self, **kwargs: Any) -> None:
        self._t = self._t + timedelta(**kwargs)


class AIRTests:
    """Test AIR (Artificial Interaction Reminder) parasocial-prevention logic."""

    def __init__(self, client: Any, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        self.base_url = getattr(client, "base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self.base_url = client._transport.base_url

        self.token = getattr(client, "api_key", None)
        if hasattr(client, "_transport") and hasattr(client._transport, "api_key"):
            self.token = client._transport.api_key

    async def run(self) -> List[Dict[str, Any]]:
        """Run all AIR tests."""
        self.console.print("\n[cyan]🛡️ Testing AIR (Artificial Interaction Reminder) System[/cyan]")

        tests = [
            ("No reminder before threshold", self.test_no_reminder_before_threshold),
            ("Message threshold fires reminder", self.test_message_threshold_fires),
            ("Reminder fires once per session", self.test_reminder_not_repeated),
            ("Time threshold fires reminder", self.test_time_threshold_fires),
            ("Idle session resets history", self.test_idle_session_reset),
            ("Non-API channels are not tracked", self.test_non_api_channels_ignored),
            ("Reminder content is correct", self.test_reminder_content),
            ("AIR wired into interact API", self.test_air_wired_into_interact_api),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:120]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _air(**kwargs: Any):
        """Construct an ArtificialInteractionReminder for in-process testing."""
        from ciris_engine.logic.services.governance.consent.air import ArtificialInteractionReminder

        return ArtificialInteractionReminder(**kwargs)

    # ------------------------------------------------------------------ #
    # In-process logic tests (deterministic, instant)
    # ------------------------------------------------------------------ #
    async def test_no_reminder_before_threshold(self) -> None:
        """No reminder may fire before the message threshold is reached."""
        air = self._air(time_service=_FakeClock(), message_threshold=20)
        for i in range(19):
            reminder = air.track_interaction("u1", "api_ch", "api", f"msg {i}")
            assert reminder is None, f"AIR reminder fired early — at message {i + 1}/19"

    async def test_message_threshold_fires(self) -> None:
        """A reminder must fire exactly at the 20-message threshold."""
        air = self._air(time_service=_FakeClock(), message_threshold=20)
        reminder = None
        for i in range(20):
            reminder = air.track_interaction("u1", "api_ch", "api", f"msg {i}")
        assert reminder is not None, "AIR reminder did NOT fire at the 20-message threshold"
        assert len(reminder) > 100, f"reminder implausibly short ({len(reminder)} chars) — not a real reminder"

    async def test_reminder_not_repeated(self) -> None:
        """The reminder fires once per session, not on every message after the threshold."""
        air = self._air(time_service=_FakeClock(), message_threshold=20)
        fired = sum(1 for i in range(40) if air.track_interaction("u1", "api_ch", "api", f"msg {i}"))
        assert fired == 1, f"reminder must fire once per session — fired {fired}× (spam)"

    async def test_time_threshold_fires(self) -> None:
        """A reminder fires after continuous interaction exceeds the time threshold."""
        clock = _FakeClock()
        # message_threshold huge so only the TIME path can trigger.
        air = self._air(time_service=clock, time_threshold_minutes=10, message_threshold=9999)
        assert air.track_interaction("u1", "api_ch", "api", "m0") is None
        clock.advance(minutes=5)  # gap < 10min idle threshold → no session reset
        assert air.track_interaction("u1", "api_ch", "api", "m1") is None, "fired before time threshold"
        clock.advance(minutes=6)  # total duration 11min ≥ 10min threshold
        reminder = air.track_interaction("u1", "api_ch", "api", "m2")
        assert reminder is not None, "no reminder after 11 min of continuous interaction (10-min threshold)"

    async def test_idle_session_reset(self) -> None:
        """An idle gap longer than the threshold resets the session's message history."""
        clock = _FakeClock()
        air = self._air(time_service=clock, time_threshold_minutes=10, message_threshold=20)
        for i in range(3):
            air.track_interaction("u1", "api_ch", "api", f"msg {i}")
        key = ("u1", "api_ch")
        assert len(air._sessions[key].message_timestamps) == 3, "expected 3 tracked messages"
        clock.advance(minutes=11)  # idle > 10-min threshold
        air.track_interaction("u1", "api_ch", "api", "after-idle")
        count = len(air._sessions[key].message_timestamps)
        assert count == 1, f"idle session did not reset — message history has {count}, expected 1"

    async def test_non_api_channels_ignored(self) -> None:
        """AIR only tracks 1:1 API channels — Discord/CLI must never trigger it."""
        air = self._air(time_service=_FakeClock(), message_threshold=2)
        for i in range(10):
            reminder = air.track_interaction("u1", "discord_ch", "discord", f"msg {i}")
            assert reminder is None, "AIR must not track non-API (discord) channels"

    async def test_reminder_content(self) -> None:
        """A fired reminder carries the expected parasocial-prevention content."""
        air = self._air(time_service=_FakeClock(), message_threshold=5)
        reminder = None
        for i in range(5):
            reminder = air.track_interaction("u1", "api_ch", "api", f"msg {i}")
        assert reminder, "reminder did not fire at the 5-message threshold"
        low = reminder.lower()
        assert "language model" in low or "tool" in low, "reminder must state it is a language model / tool"
        assert "not" in low and ("friend" in low or "substitute" in low), (
            "reminder must clarify the AI is not a friend / substitute"
        )
        assert "5 things" in low or "notice" in low, "reminder must include 5-4-3-2-1 grounding"
        assert "physical" in low or "real" in low, "reminder must reference the physical / real world"

    # ------------------------------------------------------------------ #
    # End-to-end wiring test (honest — fails loudly on a stalled endpoint)
    # ------------------------------------------------------------------ #
    async def test_air_wired_into_interact_api(self) -> None:
        """AIR must be wired into /v1/agent/interact, and a first message on a
        FRESH channel must NOT carry a reminder. A timeout ("Still processing")
        is a FAILURE — the AIR wiring cannot be verified if the agent never
        delivers a response.

        The interaction uses a unique per-run channel_id: AIR tracks message
        counts per (user, channel) session, and the shared api_<user> channel
        accumulates messages across QA modules in a batched run — so "first
        message → no reminder" only holds on a channel AIR has not seen.
        """
        import os
        import time
        import uuid

        fresh_channel = f"air_qa_smoke_{uuid.uuid4().hex[:8]}"
        parallel_mode = os.environ.get("CIRIS_QA_PARALLEL_BACKENDS") == "1"
        # Client timeout MUST stay above the server-side
        # CIRIS_API_INTERACTION_TIMEOUT (default 55s, QA-runner-bumped
        # to 180s under --parallel-backends). Otherwise the client
        # gives up before the server can deliver either a real
        # response OR its own "Still processing" timeout body.
        interact_timeout = 200.0 if parallel_mode else 70.0

        # Wall-clock the request so failure diagnostics can tell us
        # whether we hit the server-side ceiling (~180s under
        # parallel) vs. the client ceiling (200s).
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=interact_timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "message": "Hello — AIR wiring smoke test.",
                    "context": {"channel_id": fresh_channel},
                },
            )
        elapsed = time.monotonic() - t0
        assert response.status_code == 200, f"interact returned {response.status_code}: {response.text[:200]}"
        body = response.json()
        text = (body.get("data") or {}).get("response", "")

        if text.startswith("Still processing"):
            # Pull diagnostics so the failure trace tells us WHICH
            # stall this was rather than the third generic message
            # in a row. The test docstring named two distinct root
            # causes ([INTERACT_TIMEOUT] vs [STORE_RESPONSE]) and we
            # need to disambiguate.
            diag_lines: list[str] = []
            data = body.get("data") or {}
            diag_lines.append(f"channel_id={fresh_channel}")
            diag_lines.append(f"client_timeout={interact_timeout}s")
            diag_lines.append(f"parallel_backends={parallel_mode}")
            diag_lines.append(f"wall_clock={elapsed:.1f}s")
            diag_lines.append(f"server_processing_time_ms={data.get('processing_time_ms')}")
            diag_lines.append(f"server_message_id={data.get('message_id')}")
            diag_lines.append(f"server_state={data.get('state')}")

            # Best-effort live probes — these can fail without the
            # diagnostic capture being useful, so swallow exceptions.
            async with httpx.AsyncClient(timeout=5.0) as probe:
                for name, path in [
                    ("queue", "/v1/system/runtime/queue"),
                    ("health", "/v1/system/health"),
                    ("status", "/v1/system/runtime/status"),
                ]:
                    try:
                        r = await probe.get(
                            f"{self.base_url}{path}",
                            headers={"Authorization": f"Bearer {self.token}"},
                        )
                        diag_lines.append(f"{name}={r.status_code} body={r.text[:300]}")
                    except Exception as e:  # pragma: no cover — best-effort
                        diag_lines.append(f"{name}=probe-failed: {type(e).__name__}: {str(e)[:80]}")

            diag = "\n  ".join(diag_lines)
            raise AssertionError(
                "interact() returned 'Still processing' — the agent never "
                "delivered a response within the timeout. AIR API wiring is "
                "UNVERIFIABLE. This is the interact response-correlation "
                "stall (see [INTERACT_TIMEOUT] / [STORE_RESPONSE] errors in "
                "incidents), not an AIR bug.\n"
                f"  Diagnostics:\n  {diag}\n"
                "  Compare wall_clock to the server-side window: ~180s "
                "under parallel-backends means [INTERACT_TIMEOUT] "
                "(asyncio.wait_for fired); much less than that with a "
                "valid message_id present means [STORE_RESPONSE] "
                "(response stored on a channel without a registered waiter)."
            )
        assert "Mindful Interaction Reminder" not in text and "Artificial Interaction" not in text, (
            "an AIR reminder appeared on the FIRST message of a fresh channel — "
            "threshold logic regressed"
        )

    def _print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)
        self.console.print(f"\n[bold]AIR Tests: {passed}/{total} passed[/bold]")
        if passed < total:
            self.console.print("[yellow]Failed tests:[/yellow]")
            for r in self.results:
                if "FAIL" in r["status"]:
                    self.console.print(f"  - {r['test']}: {r['error']}")
