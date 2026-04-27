"""Tests for `LLMBus._maybe_capture_call` — env-gated diagnostic capture.

The capture writes captured LLM messages (potentially containing user PII /
sensitive content) to a JSONL file for replay analysis. Critical security
properties under test:

1. Disabled by default. No env var → no write, no side effects.
2. Match-required. Capture only fires when handler_name matches the env
   var (or wildcard `*`).
3. Default path is user-private, NOT /tmp/. Was previously /tmp/ — that
   default is the bug that motivated this test file.
4. Symlink-resistant. O_NOFOLLOW means a hostile pre-existing symlink
   at the output path causes the open to fail rather than redirect the
   write into the symlink target.
5. Restrictive permissions. Newly-created file is mode 0600. Newly-
   created default parent dir (~/.ciris/) is mode 0700.
6. Failure-safe-but-loud. Write errors are caught (the diagnostic must
   never crash the real LLM call) but the FIRST failure per
   (filter, path) pair logs at WARNING so misconfiguration is
   immediately visible. Subsequent failures stay at debug to avoid
   log floods.
7. First-success INFO. The first successful capture write per
   (filter, path) pair logs at INFO so operators can verify capture
   is active without tailing the file.
8. Comma-separated handler list. CIRIS_LLM_CAPTURE_HANDLER='a,b,c'
   matches handler_name in {a, b, c} — lets one run capture both DMA
   and conscience handlers without using the wildcard.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import LLMBus


class _CaptureResult(BaseModel):
    """Stand-in for a structured-output result; verifies model_dump path."""

    decision: str
    score: float


def _capture_kwargs(**overrides: Any) -> dict[str, Any]:
    """Standard kwargs for `_maybe_capture_call`. Override per test."""
    base: dict[str, Any] = {
        "handler_name": "optimization_veto_conscience",
        "service_name": "ciris_primary",
        "thought_id": "th_test",
        "task_id": "task_test",
        "messages": [
            {"role": "system", "content": "you are CIRIS-EOV"},
            {"role": "user", "content": "Proposed action: test"},
        ],
        "response_model": _CaptureResult,
        "result": _CaptureResult(decision="proceed", score=0.20),
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    base.update(overrides)
    return base


@pytest.fixture
def bus() -> LLMBus:
    """Construct an LLMBus instance without running the heavyweight
    __init__ — we're only exercising the capture method which uses only
    the module-level logger, not `self.*`."""
    return LLMBus.__new__(LLMBus)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no capture-related env vars set, and the
    process-global once-flags reset so first-success / first-failure log
    assertions are deterministic across tests."""
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_HANDLER", raising=False)
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_FILE", raising=False)
    LLMBus._capture_active_logged.clear()
    LLMBus._capture_failure_logged.clear()


# ────────────────────────────── disabled by default ──────────────────────


def test_no_env_var_no_capture(bus: LLMBus, tmp_path: Path) -> None:
    """Without CIRIS_LLM_CAPTURE_HANDLER, capture is a no-op."""
    out = tmp_path / "should_not_exist.jsonl"
    # Even though we set the explicit FILE, missing HANDLER means no write.
    os.environ["CIRIS_LLM_CAPTURE_FILE"] = str(out)
    bus._maybe_capture_call(**_capture_kwargs())
    del os.environ["CIRIS_LLM_CAPTURE_FILE"]
    assert not out.exists(), "capture wrote despite HANDLER being unset"


def test_handler_mismatch_no_capture(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HANDLER set but doesn't match handler_name → no write."""
    out = tmp_path / "no_write.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "epistemic_humility_conscience")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))
    bus._maybe_capture_call(**_capture_kwargs(handler_name="optimization_veto_conscience"))
    assert not out.exists()


def test_wildcard_matches_all_handlers(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HANDLER='*' matches any handler_name."""
    out = tmp_path / "any.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))
    for hn in ("entropy_conscience", "coherence_conscience", "optimization_veto_conscience"):
        bus._maybe_capture_call(**_capture_kwargs(handler_name=hn))
    assert out.exists()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["handler"] for r in rows] == [
        "entropy_conscience",
        "coherence_conscience",
        "optimization_veto_conscience",
    ]


def test_handler_match_fires(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact handler_name match writes one row per call."""
    out = tmp_path / "match.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "optimization_veto_conscience")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))
    bus._maybe_capture_call(**_capture_kwargs())
    bus._maybe_capture_call(**_capture_kwargs())
    assert out.exists()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2


# ────────────────────────────── default path is user-private ────────────


def test_default_path_is_under_home_not_tmp(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When CIRIS_LLM_CAPTURE_FILE is unset, the default path is under the
    user's home directory (~/.ciris/), NOT /tmp/. The previous default of
    `/tmp/llm_capture.jsonl` was a security bug — /tmp/ is world-writable
    and shared across local users on the box."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    bus._maybe_capture_call(**_capture_kwargs())

    expected = fake_home / ".ciris" / "llm_capture.jsonl"
    assert expected.is_file(), f"default path not at {expected}"

    # The default must NOT be in /tmp/
    assert not Path("/tmp/llm_capture.jsonl").samefile(expected) if (
        Path("/tmp/llm_capture.jsonl").exists()
    ) else True


def test_default_parent_dir_is_0700(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The auto-created `~/.ciris/` parent dir is mode 0700 (owner-only)."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    bus._maybe_capture_call(**_capture_kwargs())

    parent = fake_home / ".ciris"
    assert parent.is_dir()
    mode = stat.S_IMODE(parent.stat().st_mode)
    assert mode == 0o700, f"~/.ciris perms = {oct(mode)}, expected 0o700"


def test_default_file_is_0600_on_create(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The newly-created capture file is mode 0600 (owner-readable only)."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    bus._maybe_capture_call(**_capture_kwargs())

    out = fake_home / ".ciris" / "llm_capture.jsonl"
    mode = stat.S_IMODE(out.stat().st_mode)
    # umask may further restrict; we want at most 0600 (owner read+write).
    assert mode & 0o077 == 0, f"file perms {oct(mode)} grant group/other access"
    assert mode & 0o600 == 0o600, f"file perms {oct(mode)} missing owner rw"


# ────────────────────────────── symlink protection ───────────────────────


def test_symlink_at_capture_path_is_refused(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pre-existing symlink at the output path must NOT be followed.
    Hostile local user pre-creates a symlink targeting a sensitive file
    the agent uid can write; without O_NOFOLLOW the capture would clobber
    that target. With O_NOFOLLOW the open raises ELOOP and the caller
    catches it."""
    sensitive = tmp_path / "sensitive_target.txt"
    sensitive.write_text("ORIGINAL CONTENT — must not be overwritten\n")
    sensitive_before = sensitive.read_text()

    out = tmp_path / "capture.jsonl"
    out.symlink_to(sensitive)
    assert out.is_symlink()

    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))
    # Capture must not raise — the failure is logged at debug-level.
    bus._maybe_capture_call(**_capture_kwargs())

    # The symlink itself must be unchanged
    assert out.is_symlink(), "capture replaced the symlink"
    # The symlink TARGET must NOT have been written through
    assert sensitive.read_text() == sensitive_before, (
        "capture wrote through the symlink — O_NOFOLLOW is not active"
    )


def test_symlink_attack_does_not_crash_caller(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the open fails because of a symlink, the exception is caught
    so the diagnostic-only path never crashes the LLM call."""
    out = tmp_path / "trap.jsonl"
    out.symlink_to(tmp_path / "any_target.txt")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    # No exception should escape.
    bus._maybe_capture_call(**_capture_kwargs())


# ────────────────────────────── row schema ───────────────────────────────


def test_captured_row_schema(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Each JSONL row contains the expected keys with expected types."""
    out = tmp_path / "schema.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs())
    row = json.loads(out.read_text(encoding="utf-8").strip())

    assert row["handler"] == "optimization_veto_conscience"
    assert row["service"] == "ciris_primary"
    assert row["thought_id"] == "th_test"
    assert row["task_id"] == "task_test"
    assert row["response_model"] == "_CaptureResult"
    assert row["temperature"] == 0.0
    assert row["max_tokens"] == 1024
    assert isinstance(row["messages"], list)
    assert all("role" in m and "content" in m for m in row["messages"])
    assert row["result"] == {"decision": "proceed", "score": 0.20}


def test_pydantic_result_uses_model_dump(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A Pydantic-model result is serialized via model_dump (structured)."""
    out = tmp_path / "pydantic.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(
        **_capture_kwargs(result=_CaptureResult(decision="abort", score=9.5))
    )
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["result"] == {"decision": "abort", "score": 9.5}


def test_non_pydantic_result_falls_back_to_str(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-Pydantic results (no model_dump) fall back to str()."""
    out = tmp_path / "fallback.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs(result="raw string result"))
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["result"] == "raw string result"


# ────────────────────────────── append behavior ──────────────────────────


def test_multiple_calls_append_jsonl(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Successive captures append rows; existing rows are preserved."""
    out = tmp_path / "append.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs(thought_id="th_1"))
    bus._maybe_capture_call(**_capture_kwargs(thought_id="th_2"))
    bus._maybe_capture_call(**_capture_kwargs(thought_id="th_3"))

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["thought_id"] for r in rows] == ["th_1", "th_2", "th_3"]


# ────────────────────────────── failure-safe ─────────────────────────────


def test_write_failure_does_not_propagate(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the underlying write raises, the capture path swallows it.
    Diagnostic capture must never crash the real LLM call."""
    out = tmp_path / "subdir_does_not_exist" / "capture.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    # Parent dir doesn't exist — open will fail. We do NOT auto-create
    # parent dirs for explicit paths (only for the default ~/.ciris/).
    bus._maybe_capture_call(**_capture_kwargs())  # must not raise


def test_explicit_path_does_not_auto_mkdir(
    bus: LLMBus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When CIRIS_LLM_CAPTURE_FILE is explicitly set, we do NOT create
    parent dirs — that's the operator's responsibility. Auto-mkdir on
    arbitrary paths could create unintended directory hierarchies."""
    out = tmp_path / "operator_must_create_this" / "capture.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs())  # must not raise

    assert not out.parent.exists(), "auto-mkdir on explicit path"
    assert not out.exists()


# ────────────────────────────── comma-separated handler list ─────────────


def test_comma_separated_handler_list_matches_each(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HANDLER='a,b,c' matches handler_name in {a, b, c}. Lets one
    capture run grab both DMA + conscience handlers without using '*'
    (which also includes things like ActionSequenceConscience that may
    be noisy)."""
    out = tmp_path / "multi.jsonl"
    monkeypatch.setenv(
        "CIRIS_LLM_CAPTURE_HANDLER",
        "entropy_conscience,coherence_conscience,EthicalPDMAEvaluator",
    )
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    # Three matching, two non-matching
    for hn in (
        "entropy_conscience",
        "coherence_conscience",
        "EthicalPDMAEvaluator",
        "optimization_veto_conscience",  # not in list
        "ActionSequenceConscience",  # not in list
    ):
        bus._maybe_capture_call(**_capture_kwargs(handler_name=hn))

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["handler"] for r in rows] == [
        "entropy_conscience",
        "coherence_conscience",
        "EthicalPDMAEvaluator",
    ]


def test_comma_list_with_whitespace_strips(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whitespace inside the comma list is tolerated (operator-friendly)."""
    out = tmp_path / "ws.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", " entropy_conscience , coherence_conscience ")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs(handler_name="entropy_conscience"))
    bus._maybe_capture_call(**_capture_kwargs(handler_name="coherence_conscience"))
    bus._maybe_capture_call(**_capture_kwargs(handler_name="optimization_veto_conscience"))

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["handler"] for r in rows] == ["entropy_conscience", "coherence_conscience"]


def test_comma_list_with_wildcard_still_matches_all(
    bus: LLMBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If '*' appears anywhere in the comma list, treat as wildcard.
    Lets operators write 'a,b,*' to mean 'capture everything but I'm
    interested in a and b' without two separate env-var workflows."""
    out = tmp_path / "star.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "entropy_conscience,*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    bus._maybe_capture_call(**_capture_kwargs(handler_name="entropy_conscience"))
    bus._maybe_capture_call(**_capture_kwargs(handler_name="something_unrelated"))

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["handler"] for r in rows] == ["entropy_conscience", "something_unrelated"]


# ────────────────────────────── observability logs ───────────────────────


def test_first_success_logs_info_once(
    bus: LLMBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first successful capture per (filter, path) pair logs INFO so
    operators see "capture is active" in the agent's own log without
    tailing the file. Subsequent successful captures must NOT re-log
    (would flood the log on every call)."""
    out = tmp_path / "success.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    with caplog.at_level("INFO", logger="ciris_engine.logic.buses.llm_bus"):
        bus._maybe_capture_call(**_capture_kwargs())
        bus._maybe_capture_call(**_capture_kwargs())
        bus._maybe_capture_call(**_capture_kwargs())

    info_records = [r for r in caplog.records if r.levelname == "INFO" and "[LLM_CAPTURE] active" in r.getMessage()]
    assert len(info_records) == 1, (
        f"expected exactly one INFO 'active' log, got {len(info_records)}: "
        f"{[r.getMessage() for r in info_records]}"
    )
    msg = info_records[0].getMessage()
    assert str(out) in msg
    assert "filter='*'" in msg or "filter=\"*\"" in msg


def test_first_failure_logs_warning(
    bus: LLMBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first capture failure per (filter, path) logs WARNING so a
    silent misconfiguration (e.g. parent dir missing for an explicit
    path) is immediately visible — that was the exact symptom that made
    capture unreliable in production-shaped runs."""
    out = tmp_path / "missing_subdir" / "capture.jsonl"  # parent doesn't exist
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    with caplog.at_level("WARNING", logger="ciris_engine.logic.buses.llm_bus"):
        bus._maybe_capture_call(**_capture_kwargs())  # must not raise

    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "[LLM_CAPTURE]" in r.getMessage()]
    assert len(warnings) == 1, (
        f"expected exactly one WARNING on first failure, got {len(warnings)}"
    )
    msg = warnings[0].getMessage()
    assert "write failed" in msg
    assert str(out) in msg


def test_repeated_failure_logs_warning_only_once(
    bus: LLMBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Subsequent failures must NOT spam WARNING. The operator already
    saw the first one; from then on stay at debug to avoid log flood
    during a long run with persistent misconfig."""
    out = tmp_path / "missing_subdir" / "capture.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out))

    with caplog.at_level("WARNING", logger="ciris_engine.logic.buses.llm_bus"):
        for _ in range(5):
            bus._maybe_capture_call(**_capture_kwargs())  # all fail

    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "[LLM_CAPTURE]" in r.getMessage()]
    assert len(warnings) == 1, f"warning fired {len(warnings)}× — should be exactly 1"


def test_failure_warning_keyed_by_filter_and_path(
    bus: LLMBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The once-flag is keyed on (filter, path) so operators who change
    capture targets mid-process still get a fresh warning per (filter,
    path) pair. Otherwise the second misconfig would silently fail."""
    out_a = tmp_path / "missing_a" / "capture.jsonl"
    out_b = tmp_path / "missing_b" / "capture.jsonl"
    monkeypatch.setenv("CIRIS_LLM_CAPTURE_HANDLER", "*")

    with caplog.at_level("WARNING", logger="ciris_engine.logic.buses.llm_bus"):
        monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out_a))
        bus._maybe_capture_call(**_capture_kwargs())
        bus._maybe_capture_call(**_capture_kwargs())  # repeat → no warn
        monkeypatch.setenv("CIRIS_LLM_CAPTURE_FILE", str(out_b))
        bus._maybe_capture_call(**_capture_kwargs())  # new path → warn again

    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "[LLM_CAPTURE]" in r.getMessage()]
    assert len(warnings) == 2, f"expected 2 warnings (one per path), got {len(warnings)}"
    paths_in_warnings = [str(out_a) in w.getMessage() for w in warnings] + [
        str(out_b) in w.getMessage() for w in warnings
    ]
    assert any(str(out_a) in w.getMessage() for w in warnings)
    assert any(str(out_b) in w.getMessage() for w in warnings)
