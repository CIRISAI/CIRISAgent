"""Mesh-repro QA stage — drive the CIRISServer traceflow harness as an agent QA gate (#924).

The agent-tier twin of CIRISServer#258's harness/mesh-repro runner: boot the
REAL replication chain (agent node → canonical node, both from the ciris-server
substrate) on an isolated Docker bridge and assert the full trace-flow ladder
deterministically, with no remote confounds. Two tests:

  1. ``prod_wheel_test_anchor_guard`` — fast, standalone, no docker. Asserts the
     PUBLISHED ciris-server wheel installed in this interpreter does NOT carry
     the test-anchor feature (compile fence = the prod wall; test-anchor wheels
     are NEVER published). Verified forms, in order of authority:
       a. The native extension (``ciris_server/_native*.so``) exports the C
          symbol ``ciris_verify_test_anchor_compiled_in`` (the FFI surface of
          ``ciris_verify_core::test_anchor::test_anchor_compiled_in()``). When
          present it is ctypes-called and MUST return False. This is the REAL
          form on current wheels (verified against 0.5.140: symbol exported in
          .dynsym, returns False; the harness's locally built test-anchor wheel
          returns True — the guard discriminates).
       b. The Python import surface (``ciris_server`` /
          ``ciris_server._native``) exposes NO ``test_anchor_compiled_in``
          attribute on prod wheels; if one ever appears it is called and must
          return False.
     If neither the symbol nor the attribute exists (older/newer wheels), the
     guard passes on the ABSENCE form and says so.

  2. ``traceflow_harness`` — invokes ``./run_scenario.sh traceflow`` in the
     CIRISServer checkout's ``harness/mesh-repro/`` dir. The harness owns the
     whole run: test-anchor wheel (SKIP_BUILD reuse), compose lifecycle, the
     8-stage ladder (seal / trace_att / consent / converge / ship / arrive /
     summarize / score) and the verdict. The QA verdict gates on the harness
     EXIT CODE ONLY (0 = SUCCESS; 3 = stack; 10-17 = per-stage; never a log
     grep for success). The final ``[ladder]`` line is parsed into the QA
     report so a failure names its stage.

Locating the server repo:
  ``CIRIS_SERVER_REPO`` env var (default ``~/CIRISServer``). When the repo or
  the harness is missing, the stage SKIPS with a one-line message (reported as
  a PASS-variant so CI runners without the checkout stay green). Docker
  compose being unavailable skips the same way. The CIRISServer tree is only
  ever READ/EXECUTED — never modified by this module.

Env passthrough / knobs:
  - ``SKIP_BUILD`` — if unset and a wheel already exists in the harness
    ``wheels/`` dir, this module sets SKIP_BUILD=1 (the harness's own CI reuse
    path) so the run does not rebuild the substrate from the server working
    tree. Set SKIP_BUILD=0 explicitly to force a rebuild.
  - ``KEEP=1`` — passes through untouched; the harness leaves the compose
    stack up for post-mortems.
  - ``PROJECT`` — passes through (parallel-run compose project override).
  - ``CIRIS_MESH_REPRO_TIMEOUT_SECS`` — wall clock cap for the harness run
    (default 1500s; the green pipeline fits in ~15 min with images cached).

Artifacts: full harness output and the parsed verdict JSON are written to
``qa_reports/mesh_repro/`` on every run (pass or fail), so a failure carries
the harness's evidence dump without a KEEP=1 rerun.

Verifier follow-through (#924 §3): the runner stashes this module's parsed
``HarnessVerdict``; ``QARunner._verify_federation_delivery`` reuses it to
assert the trace-delta against the LOCAL harness canonical (stage 6 ``arrive``
is a direct trace_events DB count; stage 8 ``score`` is the capacity
attestation authored by a distinct identity) instead of the historical
"confirm at Node A manually" note. The manual note remains the fallback when
this stage didn't run.

WATCH-ITEM carryover (#924 §2 — documented here, deliberately NOT implemented):
  ``root-user bootstrap: store: engine is not SQLite-backed`` — seen once in
  the full-boot QA lane (job 86572430234, 2026-07-11), suspected POSTGRES
  lane: the fold's root-user bootstrap requires ``engine.sqlite_backend()``.
  Never re-ran. RE-CHECK when this stage runs against ciris-server >=0.5.118;
  if it reproduces, the fold needs a postgres-tolerant bootstrap (or a
  documented skip). Related: on Android the bootstrap outcome line is entirely
  unobservable (CIRISServer#277).

Cross-refs: CIRISAgent#924 (this stage) · CIRISServer#258 (harness, SUCCESS) ·
CIRISEdge#348 (responder seams) · CIRISPersist#451 / CIRISVerify#202
(test-anchor substrate) · #919/#920 (origin, closed) · #922 (0.5.118 tracker).

CLI:
  python3 -m tools.qa_runner mesh_repro
  CIRIS_SERVER_REPO=/path/to/CIRISServer python3 -m tools.qa_runner mesh_repro
"""
from __future__ import annotations

import ctypes
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

# ── Module-metadata contract (tools/qa_runner/modules/_module_metadata.py) ──
# The harness runs its OWN two-node compose stack; no CIRIS agent API server
# is involved, so the qa_runner must skip server start + auth entirely.
REQUIRES_LIVE_LLM = False
LIVE_LLM_DEFAULTS: Dict[str, str] = {}
SERVER_ENV: Dict[str, str] = {}
WIPE_DATA_ON_START = False
REQUIRES_CIRIS_SERVER = False

DEFAULT_SERVER_REPO = "~/CIRISServer"
SCENARIO = "traceflow"
# The pipeline takes minutes (wheel reuse + cached images ≈ 5-10 min; a cold
# docker build adds ~15 min once). 25 min is generous without being infinite.
DEFAULT_TIMEOUT_SECS = 1500.0
REPORT_DIR = Path("qa_reports/mesh_repro")

# `  [ladder] 1.seal=3 2.trace_att=1 ... 8.score=2` (lib/harness.sh
# harness_print_ladder). The harness re-samples after the loop, so the LAST
# ladder line is the authoritative final sample.
_LADDER_RE = re.compile(r"\[ladder\]((?:\s+\d+\.\w+=-?\d+)+)")
_STAGE_RE = re.compile(r"(\d+)\.(\w+)=(-?\d+)")
_BROKEN_RE = re.compile(r"BROKEN AT (\w+)")

# Stable per-stage exit codes from scenarios/traceflow.sh (EXIT_<id>), plus
# the driver's own codes — so the QA report names the stage even if the
# ladder line itself never printed (e.g. stack-up failure).
_EXIT_CODE_MEANING: Dict[int, str] = {
    0: "SUCCESS",
    2: "usage error",
    3: "stack failed to come up",
    4: "inconclusive (all stages non-zero but success stage not reached)",
    10: "seal",
    11: "trace_att",
    12: "consent",
    13: "converge",
    14: "ship",
    15: "arrive",
    16: "summarize",
    17: "score",
}


@dataclass
class HarnessVerdict:
    """Parsed outcome of one run_scenario.sh invocation.

    ``stage_counts`` maps stage id → final probe count (from the last ladder
    line). ``success`` mirrors the EXIT CODE, never a log grep.
    """

    success: bool
    exit_code: int
    ladder_line: str = ""
    stage_counts: Dict[str, int] = field(default_factory=dict)
    broken_stage: Optional[str] = None
    timed_out: bool = False
    duration_secs: float = 0.0
    log_path: Optional[str] = None


class MeshReproTests:
    """Drive the CIRISServer mesh-repro traceflow harness + prod-wheel guard."""

    REQUIRES_LIVE_LLM = REQUIRES_LIVE_LLM
    LIVE_LLM_DEFAULTS = LIVE_LLM_DEFAULTS
    SERVER_ENV = SERVER_ENV
    WIPE_DATA_ON_START = WIPE_DATA_ON_START
    REQUIRES_CIRIS_SERVER = REQUIRES_CIRIS_SERVER

    def __init__(self, client: Any, console: Console):
        # client is None by design (REQUIRES_CIRIS_SERVER=False).
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []
        # Consumed by QARunner._verify_federation_delivery (#924 §3).
        self.harness_verdict: Optional[HarnessVerdict] = None

    # ── result bookkeeping ──────────────────────────────────────────────
    def _record(self, test_name: str, passed: bool, error: Optional[str] = None, skipped: bool = False) -> None:
        # NOTE the skip encoding: the runner's module gate is
        # `all("PASS" in r["status"])`, so a skip MUST be a PASS-variant or
        # a missing CIRISServer checkout would fail CI — exactly what #924
        # says must not happen. The reason travels in `error` for reports.
        if skipped:
            status = "✅ PASS (SKIPPED)"
        elif passed:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})
        if skipped:
            self.console.print(f"  {status} {test_name}: {error}")
        elif passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[bold cyan] Mesh-Repro QA Stage (#924)[/bold cyan]")
        self.console.print("=" * 70)
        self._test_prod_wheel_guard()
        self._test_traceflow_harness()
        return self.results

    # ── 1. prod-wheel test-anchor guard ─────────────────────────────────
    def _test_prod_wheel_guard(self) -> None:
        """Assert the installed ciris-server wheel does NOT carry test-anchor.

        test_anchor_compiled_in() must be false in every published wheel
        (#924 §1 last bullet). Runs without docker or the server checkout.
        """
        name = "prod_wheel_test_anchor_guard"
        try:
            spec = importlib.util.find_spec("ciris_server")
        except (ImportError, ValueError):
            spec = None
        if spec is None or not spec.origin:
            self._record(
                name,
                True,
                error="ciris-server not installed in this interpreter — nothing to guard",
                skipped=True,
            )
            return

        pkg_dir = Path(spec.origin).parent
        try:
            wheel_version = importlib.metadata.version("ciris-server")
        except importlib.metadata.PackageNotFoundError:
            wheel_version = "unknown"

        forms_verified: List[str] = []

        # Form (b): the Python import surface. Prod wheels expose NO
        # test_anchor attribute at all — if one ever appears, it must be
        # callable-False.
        try:
            mod = importlib.import_module("ciris_server")
        except Exception as e:  # noqa: BLE001 — a broken wheel is a guard failure, not a crash
            self._record(name, False, error=f"ciris-server import failed: {e}")
            return
        py_candidates = [getattr(mod, "test_anchor_compiled_in", None)]
        try:
            native_mod = importlib.import_module("ciris_server._native")
            py_candidates.append(getattr(native_mod, "test_anchor_compiled_in", None))
        except Exception:  # noqa: BLE001 — older wheels may lay out the ext differently
            pass
        py_attr = next((c for c in py_candidates if callable(c)), None)
        if py_attr is not None:
            try:
                compiled_in = bool(py_attr())
            except Exception as e:  # noqa: BLE001
                self._record(name, False, error=f"test_anchor_compiled_in() py-call raised: {e}")
                return
            if compiled_in:
                self._record(
                    name,
                    False,
                    error=(
                        f"PROD-WALL BREACH: ciris-server {wheel_version} py-surface "
                        f"test_anchor_compiled_in() returned True — a test-anchor wheel is "
                        f"installed where the published wheel belongs ({pkg_dir})"
                    ),
                )
                return
            forms_verified.append("py-surface test_anchor_compiled_in() → False")
        else:
            forms_verified.append("py-surface: no test_anchor_compiled_in attribute (absent on prod wheels)")

        # Form (a) — the authoritative one on current wheels: the exported C
        # symbol on the native extension, ctypes-called. Verified real against
        # 0.5.140 (`nm -D` shows `T ciris_verify_test_anchor_compiled_in`).
        so_files = sorted(pkg_dir.glob("_native*.so")) or sorted(pkg_dir.glob("*.so"))
        symbol_seen = False
        for so in so_files:
            try:
                lib = ctypes.CDLL(str(so))
            except OSError as e:
                self._record(name, False, error=f"could not dlopen {so.name}: {e}")
                return
            try:
                fn = lib.ciris_verify_test_anchor_compiled_in
            except AttributeError:
                continue
            symbol_seen = True
            fn.restype = ctypes.c_bool
            fn.argtypes = []
            if bool(fn()):
                self._record(
                    name,
                    False,
                    error=(
                        f"PROD-WALL BREACH: ciris-server {wheel_version} {so.name} — "
                        f"ciris_verify_test_anchor_compiled_in() returned True: the installed "
                        f"wheel was built with --features test-anchor. Test-anchor wheels are "
                        f"NEVER published; reinstall the published wheel ({pkg_dir})"
                    ),
                )
                return
            forms_verified.append(f"{so.name}: ciris_verify_test_anchor_compiled_in() → False (ctypes)")
        if not so_files:
            forms_verified.append("no native .so found in package (pure-python layout)")
        elif not symbol_seen:
            forms_verified.append("native symbol ciris_verify_test_anchor_compiled_in absent (feature not compiled in)")

        self.console.print(f"    [dim]ciris-server {wheel_version} @ {pkg_dir}[/dim]")
        for f in forms_verified:
            self.console.print(f"    [dim]· {f}[/dim]")
        self._record(name, True)

    # ── 2. the traceflow harness run ────────────────────────────────────
    def _resolve_harness_dir(self) -> Optional[Path]:
        repo = Path(os.environ.get("CIRIS_SERVER_REPO", DEFAULT_SERVER_REPO)).expanduser()
        harness = repo / "harness" / "mesh-repro"
        if not (harness / "run_scenario.sh").is_file():
            return None
        if not (harness / "scenarios" / f"{SCENARIO}.sh").is_file():
            return None
        return harness

    @staticmethod
    def _docker_compose_available() -> bool:
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _parse_ladder(output: str) -> tuple[str, Dict[str, int]]:
        """Return (raw ladder tail, stage→count) from the LAST ladder line."""
        ladder_line = ""
        stage_counts: Dict[str, int] = {}
        matches = _LADDER_RE.findall(output)
        if matches:
            ladder_line = matches[-1].strip()
            for _idx, stage, count in _STAGE_RE.findall(ladder_line):
                stage_counts[stage] = int(count)
        return ladder_line, stage_counts

    @staticmethod
    def _first_broken_stage(output: str, stage_counts: Dict[str, int]) -> Optional[str]:
        """Name the failing stage: the harness's own BROKEN AT line if present,
        else the first zero stage after the ladder's high-water mark (mirrors
        the monotonic rule in lib/harness.sh — everything at or before the
        furthest positive stage is proven by downstream evidence)."""
        m = _BROKEN_RE.search(output)
        if m:
            return m.group(1)
        if not stage_counts:
            return None
        stages = list(stage_counts.items())  # insertion order == ladder order
        hi = -1
        for i, (_stage, count) in enumerate(stages):
            if count > 0:
                hi = i
        for i, (stage, count) in enumerate(stages):
            if i > hi and count <= 0:
                return stage
        return None

    def _test_traceflow_harness(self) -> None:
        name = "traceflow_harness"

        harness_dir = self._resolve_harness_dir()
        if harness_dir is None:
            repo_hint = os.environ.get("CIRIS_SERVER_REPO", DEFAULT_SERVER_REPO)
            self._record(
                name,
                True,
                error=(
                    f"mesh-repro harness not found under {repo_hint} "
                    f"(set CIRIS_SERVER_REPO to a CIRISServer checkout) — stage skipped"
                ),
                skipped=True,
            )
            return
        if not self._docker_compose_available():
            self._record(
                name,
                True,
                error="docker compose unavailable on this runner — stage skipped",
                skipped=True,
            )
            return

        env = dict(os.environ)
        wheels = sorted((harness_dir / "wheels").glob("ciris_server-*.whl"))
        if "SKIP_BUILD" not in env and wheels:
            # The harness's own CI reuse path: don't rebuild the substrate
            # from the (frozen) server working tree when a wheel is present.
            env["SKIP_BUILD"] = "1"
            self.console.print(f"    [dim]SKIP_BUILD=1 (reusing {wheels[-1].name})[/dim]")
        try:
            timeout_secs = float(env.get("CIRIS_MESH_REPRO_TIMEOUT_SECS", DEFAULT_TIMEOUT_SECS))
        except ValueError:
            timeout_secs = DEFAULT_TIMEOUT_SECS

        self.console.print(
            f"    [cyan]./run_scenario.sh {SCENARIO}[/cyan] [dim](cwd={harness_dir}, "
            f"timeout={timeout_secs:.0f}s, KEEP={env.get('KEEP', '0')})[/dim]"
        )

        started = time.monotonic()
        try:
            proc = subprocess.Popen(  # noqa: S603 — fixed argv, harness path validated above
                ["bash", "./run_scenario.sh", SCENARIO],
                cwd=str(harness_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,  # own process group → clean kill of compose children
            )
        except OSError as e:
            self._record(name, False, error=f"failed to launch run_scenario.sh: {e}")
            return

        output_lines: List[str] = []

        def _pump() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                output_lines.append(line)
                print(f"    │ {line}", flush=True)

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()

        timed_out = False
        while proc.poll() is None:
            if time.monotonic() - started > timeout_secs:
                timed_out = True
                self.console.print(f" [red] harness exceeded {timeout_secs:.0f}s — terminating stack[/red]")
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        pass
                    proc.wait(timeout=10)
                break
            time.sleep(2)
        pump.join(timeout=15)
        exit_code = proc.wait()
        duration = time.monotonic() - started

        output = "\n".join(output_lines)
        ladder_line, stage_counts = self._parse_ladder(output)
        broken_stage = None if (exit_code == 0 and not timed_out) else self._first_broken_stage(output, stage_counts)

        # Preserve the harness's evidence (its verdict block already includes
        # the evidence tail + per-stage diagnosis) — no KEEP=1 rerun needed.
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path: Optional[Path] = None
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            log_path = REPORT_DIR / f"{SCENARIO}_{ts}.log"
            log_path.write_text(output + "\n")
        except OSError:
            log_path = None

        # THE GATE: exit code. Never a log grep for success (lib/harness.sh
        # rule 1: a probe returns a count, the DRIVER owns the verdict).
        success = exit_code == 0 and not timed_out
        self.harness_verdict = HarnessVerdict(
            success=success,
            exit_code=exit_code,
            ladder_line=ladder_line,
            stage_counts=stage_counts,
            broken_stage=broken_stage,
            timed_out=timed_out,
            duration_secs=round(duration, 1),
            log_path=str(log_path) if log_path else None,
        )
        try:
            if log_path is not None:
                (REPORT_DIR / f"{SCENARIO}_{ts}_verdict.json").write_text(
                    json.dumps(asdict(self.harness_verdict), indent=2) + "\n"
                )
        except OSError:
            pass

        if success:
            self.console.print(f"    [green]ladder:[/green] {ladder_line or '<no ladder line captured>'}")
            self.console.print(
                f"    [green]exit=0 in {duration:.0f}s — full chain sealed → arrived → "
                f"summarized → SCORED by a distinct identity[/green]"
            )
            self._record(name, True)
        else:
            tail = "\n".join(output_lines[-25:])
            meaning = "timeout" if timed_out else _EXIT_CODE_MEANING.get(exit_code, "unknown")
            self.console.print("    [red]── harness evidence (last 25 lines) ──[/red]")
            for line in tail.splitlines():
                print(f"    ┆ {line}", flush=True)
            self._record(
                name,
                False,
                error=(
                    f"exit={exit_code} ({meaning})"
                    + (" TIMEOUT" if timed_out else "")
                    + f" broken_at={broken_stage or 'unknown'}"
                    + (f" — ladder: {ladder_line}" if ladder_line else " — no ladder line captured")
                    + (f" — full log: {log_path}" if log_path else "")
                ),
            )
