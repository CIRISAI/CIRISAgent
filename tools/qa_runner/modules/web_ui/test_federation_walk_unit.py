"""Unit tests for FederationWalkReport aggregation + serialization.

These tests do NOT require a running desktop app. They exercise the
report dataclasses, JSON roundtrip, and pretty-printer for a variety
of failure shapes — that's all that's testable without the live UI.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest

from tools.qa_runner.modules.web_ui.federation_walk_report import (
    AddPeerFlowResult,
    DiagnosticSnapshot,
    FederationWalkReport,
    HubCheckResult,
    ModeFlowResult,
    ScreenWalkResult,
    WalkStatus,
)


# ───────────────────────────────────────────────────────────────────
# ScreenWalkResult serialization
# ───────────────────────────────────────────────────────────────────
def test_screen_walk_result_defaults_are_skip() -> None:
    r = ScreenWalkResult(screen_key="identity", screen_name="Network Identity")
    assert r.status == WalkStatus.SKIP
    assert r.missing_tags == []
    assert r.clicked_targets == []
    assert r.text_probe_values == {}
    assert r.refresh_clicked is False


def test_screen_walk_result_captures_failures() -> None:
    r = ScreenWalkResult(
        screen_key="peers",
        screen_name="Network Peers",
        nav_tile="tile_federation_peers",
        root_tag="screen_federation_peers",
        status=WalkStatus.FAIL,
        reason="3 missing, 1 not clickable",
        missing_tags=["btn_filter_all", "btn_filter_canonical", "btn_filter_trusted"],
        failed_targets=["btn_add_peer"],
        diagnostic=DiagnosticSnapshot(screen="Peers", visible_tags=["x", "y"], element_count=2),
    )
    assert r.status == WalkStatus.FAIL
    assert len(r.missing_tags) == 3
    assert "btn_add_peer" in r.failed_targets
    assert r.diagnostic is not None
    assert r.diagnostic.element_count == 2


# ───────────────────────────────────────────────────────────────────
# Report aggregate counters
# ───────────────────────────────────────────────────────────────────
def _make_report_with_mixed_results() -> FederationWalkReport:
    report = FederationWalkReport()
    report.login_success = True
    report.hub_check = HubCheckResult(status=WalkStatus.PASS, reason="ok")
    report.mode_check = ModeFlowResult(status=WalkStatus.PASS, reason="ok")
    report.add_peer_check = AddPeerFlowResult(status=WalkStatus.PASS, reason="ok")
    report.per_screen.extend(
        [
            ScreenWalkResult(screen_key="identity", screen_name="Identity", status=WalkStatus.PASS),
            ScreenWalkResult(
                screen_key="peers",
                screen_name="Peers",
                status=WalkStatus.FAIL,
                missing_tags=["btn_filter_all"],
            ),
            ScreenWalkResult(screen_key="paths", screen_name="Paths", status=WalkStatus.SKIP),
            ScreenWalkResult(screen_key="announces", screen_name="Announces", status=WalkStatus.ERROR),
        ]
    )
    return report


def test_aggregate_counters() -> None:
    report = _make_report_with_mixed_results()
    assert report.total_screens == 4
    assert report.passed == 1
    assert report.failed == 1
    assert report.skipped == 1
    assert report.errored == 1
    assert report.all_passed is False
    assert report.has_any_failure is True


def test_all_passed_requires_login_and_every_step() -> None:
    r = FederationWalkReport()
    # Even with no per_screen, we need login + hub + mode + add_peer all PASS
    r.login_success = True
    r.hub_check.status = WalkStatus.PASS
    r.mode_check.status = WalkStatus.PASS
    r.add_peer_check.status = WalkStatus.PASS
    assert r.all_passed is True

    r.login_success = False
    assert r.all_passed is False

    r.login_success = True
    r.hub_check.status = WalkStatus.FAIL
    assert r.all_passed is False


def test_has_any_failure_does_not_count_skips() -> None:
    r = FederationWalkReport()
    r.per_screen.append(ScreenWalkResult(screen_key="x", screen_name="X", status=WalkStatus.SKIP))
    assert r.has_any_failure is False
    r.per_screen.append(ScreenWalkResult(screen_key="y", screen_name="Y", status=WalkStatus.FAIL))
    assert r.has_any_failure is True


# ───────────────────────────────────────────────────────────────────
# JSON roundtrip
# ───────────────────────────────────────────────────────────────────
def test_to_json_is_valid_json() -> None:
    report = _make_report_with_mixed_results()
    report.started_at = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
    report.finished_at = datetime(2026, 5, 30, 12, 0, 30, tzinfo=timezone.utc)
    s = report.to_json()
    parsed = json.loads(s)
    assert parsed["login_success"] is True
    assert parsed["passed"] == 1
    assert parsed["failed"] == 1
    assert parsed["skipped"] == 1
    assert parsed["errored"] == 1
    assert parsed["total_screens"] == 4
    # Status enum values are serialized as strings
    statuses = [s["status"] for s in parsed["per_screen"]]
    assert "PASS" in statuses
    assert "FAIL" in statuses
    assert "SKIP" in statuses
    assert "ERROR" in statuses


def test_to_json_handles_none_finished_at() -> None:
    report = FederationWalkReport()
    report.finished_at = None  # not yet completed
    s = report.to_json()
    parsed = json.loads(s)
    assert parsed["finished_at"] is None


def test_to_json_includes_missing_tags() -> None:
    report = FederationWalkReport()
    report.login_success = True
    report.hub_check = HubCheckResult(
        status=WalkStatus.FAIL,
        reason="3 hub tags missing",
        missing_tags=["text_stat_peers", "text_stat_queue", "tile_federation_map"],
    )
    payload = json.loads(report.to_json())
    assert payload["hub_check"]["missing_tags"] == [
        "text_stat_peers",
        "text_stat_queue",
        "tile_federation_map",
    ]


# ───────────────────────────────────────────────────────────────────
# print_summary
# ───────────────────────────────────────────────────────────────────
def _capture_summary(report: FederationWalkReport) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        report.print_summary()
    return buf.getvalue()


def test_print_summary_non_empty_for_all_pass() -> None:
    r = FederationWalkReport()
    r.login_success = True
    r.hub_check.status = WalkStatus.PASS
    r.mode_check.status = WalkStatus.PASS
    r.add_peer_check.status = WalkStatus.PASS
    out = _capture_summary(r)
    assert "FEDERATION WALK-TEST REPORT" in out
    assert "ALL PASSED" in out
    assert "PASS" in out


def test_print_summary_shows_missing_tags_grouped() -> None:
    r = FederationWalkReport()
    r.login_success = True
    r.hub_check.status = WalkStatus.PASS
    r.per_screen.append(
        ScreenWalkResult(
            screen_key="peers",
            screen_name="Network Peers",
            status=WalkStatus.FAIL,
            missing_tags=["btn_filter_all", "btn_add_peer"],
        )
    )
    out = _capture_summary(r)
    assert "MISSING_TAG: btn_filter_all  on  Network Peers" in out
    assert "MISSING_TAG: btn_add_peer  on  Network Peers" in out
    assert "Network Peers:" in out


def test_print_summary_shows_failed_targets_as_not_clickable() -> None:
    r = FederationWalkReport()
    r.login_success = True
    r.per_screen.append(
        ScreenWalkResult(
            screen_key="identity",
            screen_name="Network Identity",
            status=WalkStatus.FAIL,
            failed_targets=["btn_copy_signer_key"],
        )
    )
    out = _capture_summary(r)
    assert "NOT_CLICKABLE: btn_copy_signer_key" in out
    assert "testable()" in out  # the helpful hint


def test_print_summary_shows_fatal_cascade() -> None:
    r = FederationWalkReport()
    r.login_success = False
    r.fatal_reason = "login raised: connection refused"
    out = _capture_summary(r)
    assert "FATAL CASCADE" in out
    assert "login raised" in out


def test_print_summary_non_empty_for_all_failure_shapes() -> None:
    """Smoke test: every conceivable status mix should produce output."""
    shapes = [
        WalkStatus.PASS,
        WalkStatus.FAIL,
        WalkStatus.SKIP,
        WalkStatus.ERROR,
    ]
    for status in shapes:
        r = FederationWalkReport()
        r.login_success = True
        r.hub_check.status = status
        r.mode_check.status = status
        r.add_peer_check.status = status
        r.per_screen.append(ScreenWalkResult(screen_key="x", screen_name="X", status=status))
        out = _capture_summary(r)
        assert len(out) > 100, f"empty summary for status={status.value}"
        assert "FEDERATION WALK-TEST REPORT" in out


def test_print_summary_includes_mode_and_add_peer_missing_tags() -> None:
    r = FederationWalkReport()
    r.login_success = True
    r.mode_check = ModeFlowResult(
        status=WalkStatus.FAIL,
        reason="missing dialog",
        missing_tags=["dialog_mode_confirm"],
    )
    r.add_peer_check = AddPeerFlowResult(
        status=WalkStatus.FAIL,
        reason="dialog never opened",
        missing_tags=["dialog_add_peer", "btn_add_peer_submit"],
    )
    out = _capture_summary(r)
    assert "MISSING_TAG: dialog_mode_confirm  on  mode flow" in out
    assert "MISSING_TAG: dialog_add_peer  on  add-peer flow" in out
    assert "MISSING_TAG: btn_add_peer_submit  on  add-peer flow" in out


# ───────────────────────────────────────────────────────────────────
# Sanity: DiagnosticSnapshot round-trips through json via asdict
# ───────────────────────────────────────────────────────────────────
def test_diagnostic_snapshot_in_json() -> None:
    r = FederationWalkReport()
    r.login_success = True
    r.per_screen.append(
        ScreenWalkResult(
            screen_key="diagnostics",
            screen_name="Network Diagnostics",
            status=WalkStatus.FAIL,
            reason="root missing",
            diagnostic=DiagnosticSnapshot(
                screen="Network",
                visible_tags=["card_network_identity", "btn_mode_proxy"],
                element_count=2,
            ),
        )
    )
    payload = json.loads(r.to_json())
    diag = payload["per_screen"][0]["diagnostic"]
    assert diag is not None
    assert diag["screen"] == "Network"
    assert diag["visible_tags"] == ["card_network_identity", "btn_mode_proxy"]
    assert diag["element_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
