"""Report dataclasses for the federation walk-test.

These types capture the per-step results of a FederationWalkTest run.
The shape is intentionally explicit (no `Dict[str, Any]` in public APIs)
so the report is self-documenting and CI-consumable.

Status values:
- PASS:  the step completed and every required tag was present
- FAIL:  the step ran but at least one expected tag is missing / wrong
- SKIP:  a precondition failed (e.g. login broken) so the step never ran
- ERROR: an unexpected exception was raised mid-step
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ───────────────────────────────────────────────────────────────────
# Status enum
# ───────────────────────────────────────────────────────────────────
class WalkStatus(str, Enum):
    """Walk-test step status."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


# ───────────────────────────────────────────────────────────────────
# Per-step result types
# ───────────────────────────────────────────────────────────────────
@dataclass
class DiagnosticSnapshot:
    """Captured screen state used for failure diagnostics."""

    screen: str = ""
    visible_tags: List[str] = field(default_factory=list)
    element_count: int = 0


@dataclass
class HubCheckResult:
    """Result of verifying the Network hub root + required tags."""

    status: WalkStatus = WalkStatus.SKIP
    reason: str = ""
    missing_tags: List[str] = field(default_factory=list)
    diagnostic: Optional[DiagnosticSnapshot] = None


@dataclass
class ScreenWalkResult:
    """Result of walking a single federation sub-screen."""

    screen_key: str
    screen_name: str
    status: WalkStatus = WalkStatus.SKIP
    reason: str = ""
    nav_tile: str = ""
    root_tag: str = ""
    missing_tags: List[str] = field(default_factory=list)
    """Tags that were expected but not found on this screen."""

    clicked_targets: List[str] = field(default_factory=list)
    """Tags that were successfully clicked."""

    failed_targets: List[str] = field(default_factory=list)
    """Clickable tags that did not respond (likely using testable() not testableClickable())."""

    text_probe_values: Dict[str, str] = field(default_factory=dict)
    """Captured text values for diagnostic context."""

    refresh_clicked: bool = False
    diagnostic: Optional[DiagnosticSnapshot] = None


@dataclass
class ModeFlowResult:
    """Result of the agent-mode confirmation/cancel flow on the hub."""

    status: WalkStatus = WalkStatus.SKIP
    reason: str = ""
    proxy_selected: bool = False
    cancel_observed: bool = False
    client_confirmed: bool = False
    reverted_to_proxy: bool = False
    missing_tags: List[str] = field(default_factory=list)
    diagnostic: Optional[DiagnosticSnapshot] = None


@dataclass
class AddPeerFlowResult:
    """Result of the add-peer dialog flow on the Peers screen."""

    status: WalkStatus = WalkStatus.SKIP
    reason: str = ""
    dialog_opened: bool = False
    invalid_input_accepted: bool = False
    error_rendered: bool = False
    dialog_closed: bool = False
    missing_tags: List[str] = field(default_factory=list)
    diagnostic: Optional[DiagnosticSnapshot] = None


# ───────────────────────────────────────────────────────────────────
# Top-level report
# ───────────────────────────────────────────────────────────────────
@dataclass
class FederationWalkReport:
    """Aggregated report from a single FederationWalkTest.run()."""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    login_success: bool = False
    fatal_reason: str = ""
    """Set when one catastrophic failure cascades a SKIP through downstream steps."""

    hub_check: HubCheckResult = field(default_factory=HubCheckResult)
    per_screen: List[ScreenWalkResult] = field(default_factory=list)
    mode_check: ModeFlowResult = field(default_factory=ModeFlowResult)
    add_peer_check: AddPeerFlowResult = field(default_factory=AddPeerFlowResult)

    # ─── Aggregate counters ────────────────────────────────────────
    @property
    def total_screens(self) -> int:
        return len(self.per_screen)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.per_screen if r.status == WalkStatus.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.per_screen if r.status == WalkStatus.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.per_screen if r.status == WalkStatus.SKIP)

    @property
    def errored(self) -> int:
        return sum(1 for r in self.per_screen if r.status == WalkStatus.ERROR)

    @property
    def all_passed(self) -> bool:
        """True only if every checked step is PASS (no FAIL / no SKIP / no ERROR)."""
        if not self.login_success:
            return False
        if self.hub_check.status != WalkStatus.PASS:
            return False
        if self.mode_check.status != WalkStatus.PASS:
            return False
        if self.add_peer_check.status != WalkStatus.PASS:
            return False
        return all(r.status == WalkStatus.PASS for r in self.per_screen)

    @property
    def has_any_failure(self) -> bool:
        """True if anything FAILED or ERRORED (SKIPs from cascade don't count alone)."""
        if self.hub_check.status in (WalkStatus.FAIL, WalkStatus.ERROR):
            return True
        if self.mode_check.status in (WalkStatus.FAIL, WalkStatus.ERROR):
            return True
        if self.add_peer_check.status in (WalkStatus.FAIL, WalkStatus.ERROR):
            return True
        return any(r.status in (WalkStatus.FAIL, WalkStatus.ERROR) for r in self.per_screen)

    # ─── Serialization ─────────────────────────────────────────────
    def to_json(self) -> str:
        """Serialize the full report as a JSON string."""

        def _serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(f"Unserializable: {type(obj).__name__}")

        payload = {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "login_success": self.login_success,
            "fatal_reason": self.fatal_reason,
            "total_screens": self.total_screens,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errored": self.errored,
            "all_passed": self.all_passed,
            "hub_check": asdict(self.hub_check),
            "per_screen": [asdict(r) for r in self.per_screen],
            "mode_check": asdict(self.mode_check),
            "add_peer_check": asdict(self.add_peer_check),
        }
        return json.dumps(payload, default=_serialize, indent=2)

    # ─── Pretty-printer ────────────────────────────────────────────
    def print_summary(self) -> None:
        """Pretty-print the report to stdout.

        Plain-text only (CIRIS CLAUDE.md prefers no emojis unless requested).
        """
        lines: List[str] = []
        lines.append("=" * 70)
        lines.append("FEDERATION WALK-TEST REPORT")
        lines.append("=" * 70)
        lines.append(f"  started:       {self.started_at.isoformat()}")
        if self.finished_at:
            duration = (self.finished_at - self.started_at).total_seconds()
            lines.append(f"  finished:      {self.finished_at.isoformat()}  ({duration:.2f}s)")
        lines.append(f"  login:         {'PASS' if self.login_success else 'FAIL'}")
        if self.fatal_reason:
            lines.append(f"  FATAL CASCADE: {self.fatal_reason}")
        lines.append("")

        # Hub
        lines.append(f"  hub:           {self.hub_check.status.value}    {self.hub_check.reason}")
        if self.hub_check.missing_tags:
            for tag in self.hub_check.missing_tags:
                lines.append(f"      MISSING_TAG: {tag}  on  Network hub")
        lines.append("")

        # Per-screen table
        lines.append("  per-screen:")
        for r in self.per_screen:
            lines.append(f"    {r.status.value:5s}  {r.screen_name:30s}  {r.reason}")
        lines.append("")

        # Missing tags, grouped by screen
        any_missing = any(r.missing_tags for r in self.per_screen)
        if any_missing:
            lines.append("  missing tags (action items for Compose tag-pass):")
            for r in self.per_screen:
                if not r.missing_tags:
                    continue
                lines.append(f"    {r.screen_name}:")
                for tag in r.missing_tags:
                    lines.append(f"      MISSING_TAG: {tag}  on  {r.screen_name}")
            lines.append("")

        # Failed clickable targets — likely testable() vs testableClickable()
        any_failed_clicks = any(r.failed_targets for r in self.per_screen)
        if any_failed_clicks:
            lines.append("  clickable targets that did not respond:")
            lines.append("    (likely using testable() — needs testableClickable())")
            for r in self.per_screen:
                if not r.failed_targets:
                    continue
                lines.append(f"    {r.screen_name}:")
                for tag in r.failed_targets:
                    lines.append(f"      NOT_CLICKABLE: {tag}")
            lines.append("")

        # Mode flow
        lines.append(f"  mode flow:     {self.mode_check.status.value}  {self.mode_check.reason}")
        if self.mode_check.missing_tags:
            for tag in self.mode_check.missing_tags:
                lines.append(f"      MISSING_TAG: {tag}  on  mode flow")
        lines.append("")

        # Add-peer flow
        lines.append(f"  add-peer flow: {self.add_peer_check.status.value}  {self.add_peer_check.reason}")
        if self.add_peer_check.missing_tags:
            for tag in self.add_peer_check.missing_tags:
                lines.append(f"      MISSING_TAG: {tag}  on  add-peer flow")
        lines.append("")

        # Aggregate counters
        lines.append(
            f"  totals:   passed={self.passed}  failed={self.failed}  "
            f"skipped={self.skipped}  errored={self.errored}  total={self.total_screens}"
        )
        lines.append(f"  verdict:  {'ALL PASSED' if self.all_passed else 'FAILURES PRESENT'}")
        lines.append("=" * 70)
        print("\n".join(lines))
