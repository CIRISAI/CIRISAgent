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
6. Failure-safe. Write errors are swallowed at debug-log level — the
   caller (real LLM call) must not crash because of a diagnostic
   capture failure.
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
    """Each test starts with no capture-related env vars set."""
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_HANDLER", raising=False)
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_FILE", raising=False)


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
