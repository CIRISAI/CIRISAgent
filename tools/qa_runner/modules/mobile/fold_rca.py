"""
Fold-Failure RCA for the CIRIS Mobile QA Runner

When an Android QA run fails (especially anywhere in the node-fold /
first-run chain), this module inspects the device's diagnostics — the
Python runtime log, incidents log, Rust substrate logs (ciris-server.log*),
filtered logcat, process liveness, and live port probes on 4243/8080 —
and classifies WHICH layer broke, with the evidence lines, instead of
leaving a bare FAIL.

Everything is best-effort: every probe is individually wrapped so a dead
emulator, a release build (no run-as), or a missing log degrades to
"evidence unavailable" rather than an exception. run_fold_rca() itself
never raises — on internal error it returns an "rca-error" verdict so the
original suite failure is never masked.

Verdict layers (decision tree — first confirmed match wins, but secondary
flags are always collected):

  fold-panic            serve_with_python_adapter panicked
                        (CIRISServer#264 class — file the panic location)
  compose-hang          bind-window failure + process alive + 4243 still
                        refused at RCA time (CIRISServer#279)
  bind-window           bind-window failure but 4243 answers NOW —
                        compose completed after the window; raise it
  pin-mint-or-accessor  fold bound (LISTENING on 4243) but the node_fold
                        one-time CLAIM PIN echo never appeared
                        (CIRISServer#277 — accessor returned None)
  pin-capture-client    PIN echo present in the python log but Kotlin
                        never logged the capture (agent-side bug)
  node-session-401      mintUserIdentity rejected 401 invalid/expired session
  rooting               [DELIVERY-PROBE] canonical did not root
  kex-reply-path        ROOTED but KEX still None (peer side)
  seal-consent-or-llm   KEX PRESENT + SPEAK but no TRACE SEALED
  fold-healthy          LISTENING on 4243 and nothing above matched —
                        failure is above the fold; see the suite report

Secondary flags (attached to any verdict):

  rust_sink_dark        [RUST-SINK] DARK in the python log, OR the dated
                        ciris-server.log.<date> is 0 bytes while .boot has
                        bytes — substrate diagnostics lost
                        (CIRISServer#279 ask 1)
  first_run_loop        >=3 "Startup READY" -> "first-run - showing login"
                        cycles within 2 min — node unclaimed, first-run
                        status stuck true

Usage (live):
    from .adb_helper import ADBHelper
    from .fold_rca import run_fold_rca, format_rca
    adb = ADBHelper(device_serial="emulator-5556")
    result = run_fold_rca(adb, package="ai.ciris.mobile.debug")
    print(format_rca(result))

Usage (offline, against a pulled-logs directory from pull_device_logs):
    result = run_fold_rca(None, logs_dir="client_qa_reports/firstrun_pin/<ts>")
"""

import glob
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

# ── Signature patterns (verified against real device logs) ──────────────────

SIG_PANIC = re.compile(r"serve_with_python_adapter panicked", re.I)
SIG_PANIC_AT = re.compile(r"\[at ([^\]]+)\]")
SIG_BIND_FAIL = re.compile(r"read-API did not bind 127\.0\.0\.1:4243 in the bind window", re.I)
SIG_LISTENING = re.compile(r"LISTENING on 4243", re.I)
SIG_RUST_SINK_DARK = re.compile(r"\[RUST-SINK\] DARK", re.I)
SIG_PIN_NOT_CAPTURED = re.compile(r"claim PIN not captured", re.I)
SIG_PIN_ECHO = re.compile(r"one-time CLAIM PIN", re.I)
SIG_PIN_KOTLIN_CAPTURED = re.compile(r"Captured one-time CLAIM PIN", re.I)
SIG_MINT_IDENTITY = re.compile(r"mintUserIdentity", re.I)
SIG_SESSION_401 = re.compile(r"invalid or expired session", re.I)
SIG_MINT_CONNREFUSED = re.compile(r"ConnectException.*4243", re.I)
SIG_NAV_READY = re.compile(r"Startup READY, checking first-run status", re.I)
SIG_NAV_LOGIN = re.compile(r"Mobile first-run - showing login", re.I)
SIG_DELIVERY_NO_ROOT = re.compile(r"\[DELIVERY-PROBE\].*did not root", re.I)
SIG_KEX_NONE = re.compile(r"ROOTED but KEX still None", re.I)
SIG_KEX_PRESENT = re.compile(r"KEX PRESENT", re.I)
SIG_SPEAK = re.compile(r"\bSPEAK\b")
SIG_TRACE_SEALED = re.compile(r"TRACE SEALED", re.I)
SIG_CONSENT = re.compile(r"consent_blocked|NoConsent", re.I)
SIG_LLM_ERROR = re.compile(r"(model_not_available|\b401\b|\b404\b|\b429\b)", re.I)
SIG_LLM_CONTEXT = re.compile(r"llm|openrouter|openai|groq|together|deepinfra", re.I)

# logcat -v time timestamp: "07-15 20:24:07.653 ..."
LOGCAT_TS = re.compile(r"^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})")

LOGS_DIR_ON_DEVICE = "files/ciris/logs"
LOGCAT_TAGS = [
    "SetupViewModel:*",
    "CIRISApiClient:*",
    "MainActivity:*",
    "PythonRuntime:*",
    "CIRISApp:*",
    "StartupViewModel:*",
    "*:S",
]

MAX_EVIDENCE_LINES = 12
MAX_LINE_WIDTH = 220


# ── Best-effort collection helpers ───────────────────────────────────────────


def _adb_out(adb, args: List[str], timeout: int = 30) -> str:
    """Run an adb command, returning stdout or '' on any failure."""
    try:
        result = adb._run_adb(args, timeout=timeout)
        return result.stdout or ""
    except Exception:
        return ""


def _run_as(adb, package: str, cmd: str, timeout: int = 30) -> str:
    """Run a shell command as the debug package, '' on any failure.

    The command must be wrapped as ONE quoted string: adb joins its args
    with spaces and the device shell re-splits them, so an unquoted
    `sh -c readlink path` would run bare `readlink` with no arguments.
    (cmd must not contain single quotes.)
    """
    return _adb_out(adb, ["shell", f"run-as {package} sh -c '{cmd}'"], timeout=timeout)


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _probe_port(adb, device_port: int, path: str = "/v1/health") -> Tuple[str, bool]:
    """
    Probe a device-local port via `adb forward` + HTTP GET.

    Returns (human_result, answering). Any HTTP response (even 4xx/5xx)
    means the port is answering; connection reset / remote-disconnected /
    timeout means it is not (adb forward accepts locally, then closes when
    the device-side connect is refused).
    """
    local_port = _pick_free_port()
    try:
        _adb_out(adb, ["forward", f"tcp:{local_port}", f"tcp:{device_port}"])
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{local_port}{path}", timeout=5)
            return f"HTTP {resp.status}", True
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}", True  # server answered — port is bound
        except Exception as e:
            return f"refused/no-answer ({type(e).__name__})", False
    finally:
        _adb_out(adb, ["forward", "--remove", f"tcp:{local_port}"])


def _parse_rust_ls(ls_output: str) -> Dict[str, int]:
    """Parse `ls -la .../ciris-server.log*` output into {basename: size}."""
    sizes: Dict[str, int] = {}
    for line in ls_output.splitlines():
        parts = line.split()
        # -rw------- 1 u0_a244 u0_a244 192 2026-07-15 20:24 /...path.../ciris-server.log.boot
        if len(parts) >= 8 and "ciris-server.log" in parts[-1]:
            try:
                sizes[os.path.basename(parts[-1])] = int(parts[4])
            except (ValueError, IndexError):
                continue
    return sizes


def _humanize_etime(etime: str) -> str:
    """Turn ps ETIME ([[dd-]hh:]mm:ss) into e.g. '17m16s' / '1d2h3m4s'."""
    etime = etime.strip()
    m = re.match(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$", etime)
    if not m:
        return etime or "unknown"
    days, hours, mins, secs = m.groups()
    out = ""
    if days:
        out += f"{int(days)}d"
    if hours:
        out += f"{int(hours)}h"
    return out + f"{int(mins)}m{int(secs)}s"


def _collect_live(adb, package: str) -> Dict:
    """Gather all evidence sources from a live device. Every step best-effort."""
    ev: Dict = {
        "mode": "live",
        "pid": None,
        "etime": None,
        "python_log": "",
        "python_log_name": "",
        "incidents": "",
        "rust_sizes": {},
        "rust_content": {},
        "logcat": "",
        "port_4243": "not probed",
        "port_4243_open": None,
        "port_8080": "not probed",
        "port_8080_open": None,
    }

    # Liveness
    pid = _adb_out(adb, ["shell", "pidof", package]).strip()
    if pid:
        ev["pid"] = pid.split()[0]
        ev["etime"] = _adb_out(adb, ["shell", "ps", "-p", ev["pid"], "-o", "ETIME="]).strip()

    # Python runtime log: resolve latest.log symlink, fall back to newest dated log
    log_name = _run_as(adb, package, f"readlink {LOGS_DIR_ON_DEVICE}/latest.log").strip()
    if not log_name:
        listing = _run_as(adb, package, f"ls -t {LOGS_DIR_ON_DEVICE}/ciris_agent_*.log 2>/dev/null")
        names = [os.path.basename(l.strip()) for l in listing.splitlines() if l.strip()]
        log_name = names[0] if names else "latest.log"
    ev["python_log_name"] = log_name
    ev["python_log"] = _run_as(adb, package, f"cat {LOGS_DIR_ON_DEVICE}/{log_name}", timeout=60)
    if not ev["python_log"] and log_name != "latest.log":
        ev["python_log"] = _run_as(adb, package, f"cat {LOGS_DIR_ON_DEVICE}/latest.log", timeout=60)

    # Incidents
    ev["incidents"] = _run_as(adb, package, f"cat {LOGS_DIR_ON_DEVICE}/incidents_latest.log", timeout=60)

    # Rust substrate logs: sizes always, content only when small and non-empty
    rust_ls = _run_as(adb, package, f"ls -la {LOGS_DIR_ON_DEVICE}/ciris-server.log* 2>/dev/null")
    ev["rust_sizes"] = _parse_rust_ls(rust_ls)
    for name, size in ev["rust_sizes"].items():
        if 0 < size <= 20000:
            ev["rust_content"][name] = _run_as(adb, package, f"cat {LOGS_DIR_ON_DEVICE}/{name}")

    # Filtered logcat
    ev["logcat"] = _adb_out(adb, ["logcat", "-d", "-v", "time"] + LOGCAT_TAGS, timeout=60)

    # Live port probes
    ev["port_4243"], ev["port_4243_open"] = _probe_port(adb, 4243, "/v1/health")
    ev["port_8080"], ev["port_8080_open"] = _probe_port(adb, 8080, "/v1/system/health")

    return ev


def _read_file(path: str) -> str:
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _collect_offline(logs_dir: str) -> Dict:
    """Gather evidence from a pulled-logs directory (pull_device_logs layout)."""
    ev: Dict = {
        "mode": f"offline ({logs_dir})",
        "pid": None,
        "etime": None,
        "python_log": "",
        "python_log_name": "",
        "incidents": "",
        "rust_sizes": {},
        "rust_content": {},
        "logcat": "",
        "port_4243": "not probed (offline)",
        "port_4243_open": None,
        "port_8080": "not probed (offline)",
        "port_8080_open": None,
    }

    logs_sub = os.path.join(logs_dir, "logs")
    candidates = [os.path.join(logs_sub, "latest.log")]
    candidates += sorted(glob.glob(os.path.join(logs_sub, "ciris_agent_*.log")), reverse=True)
    for path in candidates:
        content = _read_file(path)
        if content:
            ev["python_log"] = content
            ev["python_log_name"] = os.path.basename(path)
            break

    ev["incidents"] = _read_file(os.path.join(logs_sub, "incidents_latest.log"))

    for path in glob.glob(os.path.join(logs_sub, "ciris-server.log*")):
        name = os.path.basename(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        ev["rust_sizes"][name] = size
        if 0 < size <= 20000:
            ev["rust_content"][name] = _read_file(path)

    for logcat_name in ("logcat_app.txt", "logcat_combined.txt"):
        content = _read_file(os.path.join(logs_dir, logcat_name))
        if content:
            ev["logcat"] = content
            break

    return ev


# ── Classification ───────────────────────────────────────────────────────────


def _grep(text: str, pattern: re.Pattern) -> List[str]:
    return [line.strip() for line in text.splitlines() if pattern.search(line)]


def _logcat_ts_seconds(line: str) -> Optional[float]:
    """Approx seconds-of-year from a logcat -v time line (good enough for windows)."""
    m = LOGCAT_TS.match(line)
    if not m:
        return None
    month, day, hh, mm, ss, ms = (int(g) for g in m.groups())
    return ((month * 31 + day) * 86400.0) + hh * 3600 + mm * 60 + ss + ms / 1000.0


def _detect_first_run_loop(logcat: str) -> Tuple[bool, int]:
    """>=3 READY->login cycles within any 2-minute window."""
    login_ts = []
    ready_count = 0
    for line in logcat.splitlines():
        if SIG_NAV_READY.search(line):
            ready_count += 1
        elif SIG_NAV_LOGIN.search(line):
            ts = _logcat_ts_seconds(line)
            if ts is not None:
                login_ts.append(ts)
    if ready_count < 3 or len(login_ts) < 3:
        return False, 0
    login_ts.sort()
    best = 0
    for i, start in enumerate(login_ts):
        in_window = sum(1 for t in login_ts[i:] if t - start <= 120.0)
        best = max(best, in_window)
    return best >= 3, best


def _detect_rust_sink_dark(ev: Dict) -> Tuple[bool, str]:
    dark_lines = _grep(ev["python_log"], SIG_RUST_SINK_DARK)
    if dark_lines:
        return True, dark_lines[0]
    boot_size = ev["rust_sizes"].get("ciris-server.log.boot", 0)
    dated = {n: s for n, s in ev["rust_sizes"].items() if re.search(r"ciris-server\.log\.\d{4}-\d{2}-\d{2}$", n)}
    if boot_size > 0 and dated and all(s == 0 for s in dated.values()):
        names = ", ".join(f"{n}={s}B" for n, s in sorted(dated.items()))
        return True, f"dated rust log 0 bytes while .boot={boot_size}B ({names})"
    return False, ""


def _clip(line: str) -> str:
    line = line.strip()
    return line if len(line) <= MAX_LINE_WIDTH else line[: MAX_LINE_WIDTH - 1] + "…"


def _classify(ev: Dict) -> Dict:
    """Walk the decision tree. First confirmed match wins; flags always collected."""
    py = ev["python_log"]
    lc = ev["logcat"]
    evidence: List[str] = []
    flags: List[str] = []
    flag_notes: List[str] = []

    def add(source: str, lines, limit: int = 2):
        if isinstance(lines, str):
            lines = [lines]
        for line in lines[:limit]:
            if line:
                evidence.append(f"{source:<6}| {_clip(line)}")

    # Secondary flags first — they attach to any verdict
    sink_dark, sink_why = _detect_rust_sink_dark(ev)
    if sink_dark:
        flags.append("rust_sink_dark")
        flag_notes.append(f"rust  | {_clip(sink_why)} — substrate diagnostics lost (CIRISServer#279 ask 1)")

    loop_detected, loop_count = _detect_first_run_loop(lc)
    if loop_detected:
        flags.append("first_run_loop")
        flag_notes.append(
            f"logcat| first-run loop: {loop_count} READY→login cycles in 2min — "
            "node unclaimed → first-run status stuck true"
        )

    mint_refused = [l for l in lc.splitlines() if SIG_MINT_IDENTITY.search(l) and SIG_MINT_CONNREFUSED.search(l)]
    if mint_refused:
        flags.append("mint_connect_refused")
        flag_notes.append(f"logcat| {_clip(mint_refused[0])} — fold never bound during the wizard")

    panic_lines = _grep(py, SIG_PANIC)
    bind_fail_lines = _grep(py, SIG_BIND_FAIL)
    listening = bool(SIG_LISTENING.search(py))
    alive = ev["pid"] is not None
    etime_h = _humanize_etime(ev["etime"] or "")

    verdict = layer = next_action = upstream_ref = ""

    # 1. fold-panic
    if panic_lines:
        verdict = "fold-panic"
        at = SIG_PANIC_AT.search(panic_lines[0])
        location = at.group(1) if at else "location not present in panic line"
        layer = f"read-API task panicked inside serve_with_python_adapter [at {location}]"
        upstream_ref = "CIRISServer#264 class — file with the panic location"
        next_action = f"file the panic location upstream ({location})"
        add("py", panic_lines)

    # 2/3. bind-window failure family
    elif bind_fail_lines:
        add("py", bind_fail_lines, limit=1)
        # 0.5.120 (CIRISServer#279): node_fold polls compose_status() during
        # the bind wait and logs "[COMPOSE] phase: <name> (<Ns> [STUCK])"
        # transitions, and the bind-window error carries "compose phase at
        # expiry: <name>". Extract the NAMED wedged phase so the verdict says
        # WHERE compose stopped, not just that it did.
        compose_lines = _grep(py, re.compile(r"\[COMPOSE\] phase:|compose phase at expiry:", re.IGNORECASE))
        wedged_phase = None
        if compose_lines:
            m = re.search(r"compose phase at expiry:\s*([^\n]+)", compose_lines[-1]) or re.search(
                r"\[COMPOSE\] phase:\s*([^\n]+)", compose_lines[-1]
            )
            wedged_phase = m.group(1).strip() if m else None
            add("py", compose_lines, limit=3)
        if ev["port_4243_open"]:
            verdict = "bind-window"
            layer = "4243 IS answering now — compose completed after the bind window"
            next_action = (
                "raise the mobile bind window / Start-Adapters timeout — compose completed after the window"
            )
            add("live", f"127.0.0.1:4243 → {ev['port_4243']}")
        elif alive and ev["port_4243_open"] is False:
            verdict = "compose-hang"
            layer = f"node compose never completed — serve alive {etime_h}, 4243 refused"
            if wedged_phase:
                layer += f"; WEDGED IN PHASE: {wedged_phase}"
            upstream_ref = "CIRISServer#279"
            next_action = (
                f"file the wedged phase ({wedged_phase}) on CIRISServer#279"
                if wedged_phase
                else "attach this RCA + rust substrate logs (if any) to CIRISServer#279; "
                "the compose future never resolved inside the fold"
            )
            add("live", f"pid {ev['pid']} alive, ETIME {ev['etime'] or 'unknown'} ({etime_h})")
            add("live", f"127.0.0.1:4243 → {ev['port_4243']}")
            add("live", f"127.0.0.1:8080 → {ev['port_8080']}")
        else:
            verdict = "bind-failure"
            state = "process no longer alive" if ev["port_4243_open"] is not None else "liveness/port unknown (offline)"
            layer = f"node fold failed to bind 4243; {state} — cannot separate compose-hang from bind-window"
            upstream_ref = "CIRISServer#279 (unconfirmed — no live process to probe)"
            next_action = "re-run leaving the app alive, then re-run RCA live to separate compose-hang vs bind-window"
            if alive:
                add("live", f"pid {ev['pid']} alive, ETIME {ev['etime'] or 'unknown'}")
            add("live", f"127.0.0.1:4243 → {ev['port_4243']}")

    # 5 (spec order). CLAIM PIN layers — fold bound but PIN never reached Kotlin
    elif (SIG_PIN_NOT_CAPTURED.search(lc) or SIG_PIN_NOT_CAPTURED.search(py)) and listening:
        pin_lines = _grep(lc, SIG_PIN_NOT_CAPTURED) or _grep(py, SIG_PIN_NOT_CAPTURED)
        echo_lines = _grep(py, SIG_PIN_ECHO)
        if not echo_lines:
            verdict = "pin-mint-or-accessor"
            layer = "fold bound (LISTENING on 4243) but node_fold never echoed the one-time CLAIM PIN"
            upstream_ref = "CIRISServer#277 — accessor returned None (node already owned? mint skipped?)"
            next_action = "check node ownership state in the substrate; file on CIRISServer#277 if mint was skipped"
        elif not SIG_PIN_KOTLIN_CAPTURED.search(lc):
            verdict = "pin-capture-client"
            layer = "python echoed the one-time CLAIM PIN but Kotlin never logged 'Captured one-time CLAIM PIN'"
            upstream_ref = "CIRISAgent — client-side PIN capture bug (file on CIRISAgent)"
            next_action = "debug the Kotlin node-log tail / PIN capture path in the agent client"
            add("py", echo_lines, limit=1)
        else:
            verdict = "pin-timing"
            layer = "PIN echoed and captured, yet a 'claim PIN not captured' was also logged — likely stale/racing waits"
            next_action = "inspect timestamps of the echo vs the capture vs the wait deadline"
            add("py", echo_lines, limit=1)
        add("logcat", pin_lines)
        add("py", _grep(py, SIG_LISTENING), limit=1)

    # 6. claim-401 / session
    elif any(SIG_MINT_IDENTITY.search(l) and "401" in l for l in lc.splitlines()) or (
        SIG_MINT_IDENTITY.search(lc) and SIG_SESSION_401.search(lc)
    ):
        verdict = "node-session-401"
        layer = "mintUserIdentity rejected with 401 (invalid or expired session)"
        next_action = "re-establish the node session before the mint call; check session TTL vs wizard duration"
        add("logcat", [l for l in _grep(lc, SIG_MINT_IDENTITY) if "401" in l or SIG_SESSION_401.search(l)], limit=3)
        add("logcat", _grep(lc, SIG_SESSION_401), limit=2)

    # 8. delivery layers — only meaningful when the fold itself is fine
    elif listening and _grep(py, SIG_DELIVERY_NO_ROOT):
        verdict = "rooting"
        layer = "canonical delivery probe did not root — replication tree never formed"
        next_action = "check edge peering / bootstrap_peers; the canonical never rooted"
        add("py", _grep(py, SIG_DELIVERY_NO_ROOT))
    elif listening and _grep(py, SIG_KEX_NONE):
        verdict = "kex-reply-path"
        layer = "canonical ROOTED but KEX still None — peer-side reply path broken"
        next_action = "inspect the PEER's kex responder — the reply never arrived (peer side)"
        add("py", _grep(py, SIG_KEX_NONE))
    elif (
        listening
        and _grep(py, SIG_KEX_PRESENT)
        and _grep(py, SIG_SPEAK)
        and not _grep(py, SIG_TRACE_SEALED)
    ):
        verdict = "seal-consent-or-llm"
        layer = "KEX PRESENT and agent SPOKE but no TRACE SEALED — seal blocked by consent or LLM failure"
        next_action = "check consent state and LLM provider health below"
        add("py", _grep(py, SIG_KEX_PRESENT), limit=1)
        consent_lines = _grep(py, SIG_CONSENT) + _grep(ev["incidents"], SIG_CONSENT)
        add("py", consent_lines, limit=2)
        llm_lines = [
            l
            for l in (py + "\n" + ev["incidents"]).splitlines()
            if SIG_LLM_ERROR.search(l) and SIG_LLM_CONTEXT.search(l)
        ]
        add("py", llm_lines, limit=3)

    # 9. healthy fold
    elif listening:
        verdict = "fold-healthy"
        layer = "fold healthy — failure is above the fold; see suite report"
        next_action = "the node fold is fine; debug the failing test at the UI/API layer (see suite report)"
        add("py", _grep(py, SIG_LISTENING), limit=1)

    else:
        verdict = "inconclusive"
        layer = "no known fold signature matched and no LISTENING on 4243 — python log may be missing/truncated"
        next_action = "pull full device logs (pull_device_logs) and inspect manually"
        if not py:
            add("live", "python runtime log unavailable (run-as failed? release build?)")
        if alive:
            add("live", f"pid {ev['pid']} alive, ETIME {ev['etime'] or 'unknown'}")
        add("live", f"127.0.0.1:4243 → {ev['port_4243']}")

    evidence.extend(flag_notes)
    if len(evidence) > MAX_EVIDENCE_LINES:
        extra = len(evidence) - MAX_EVIDENCE_LINES
        evidence = evidence[:MAX_EVIDENCE_LINES] + [f"      | … (+{extra} more lines)"]

    return {
        "verdict": verdict,
        "layer": layer,
        "evidence": evidence,
        "next_action": next_action,
        "upstream_ref": upstream_ref,
        "flags": flags,
        "mode": ev["mode"],
        "python_log_name": ev["python_log_name"],
    }


# ── Public API ───────────────────────────────────────────────────────────────


def run_fold_rca(adb, package: str = "ai.ciris.mobile.debug", logs_dir: Optional[str] = None) -> dict:
    """
    Run the fold-failure RCA against a live device (via ADBHelper) or,
    when logs_dir is given, against a pulled-logs directory (offline mode).

    Never raises: on internal error returns an 'rca-error' verdict so the
    original suite failure is never masked.

    Returns:
        {verdict, layer, evidence: [lines], next_action, upstream_ref,
         flags: [names], mode, python_log_name}
    """
    try:
        if logs_dir:
            ev = _collect_offline(logs_dir)
        else:
            ev = _collect_live(adb, package)
        return _classify(ev)
    except Exception as e:
        return {
            "verdict": "rca-error",
            "layer": f"RCA itself failed: {type(e).__name__}: {e}",
            "evidence": [],
            "next_action": "inspect the suite report and pulled logs manually",
            "upstream_ref": "",
            "flags": [],
            "mode": "error",
            "python_log_name": "",
        }


def format_rca(result: dict) -> str:
    """Render the RCA result as a compact terminal block."""
    verdict = result.get("verdict", "unknown")
    upstream = result.get("upstream_ref", "")
    header = f"{verdict} ({upstream})" if upstream else verdict

    lines = [
        "════ FOLD RCA ════",
        f"VERDICT : {header}",
        f"LAYER   : {result.get('layer', '')}",
    ]
    flags = result.get("flags", [])
    if flags:
        lines.append(f"FLAGS   : {', '.join(flags)}")
    evidence = result.get("evidence", [])
    if evidence:
        lines.append("EVIDENCE:")
        lines.extend(f"  | {line}" for line in evidence)
    if result.get("next_action"):
        lines.append(f"NEXT    : {result['next_action']}")
    lines.append("══════════════════")
    return "\n".join(lines)


def format_rca_markdown(result: dict) -> str:
    """Render the RCA result as markdown (same content as format_rca)."""
    verdict = result.get("verdict", "unknown")
    upstream = result.get("upstream_ref", "")
    header = f"{verdict} ({upstream})" if upstream else verdict

    lines = [
        "# Fold RCA",
        "",
        f"**Verdict**: {header}",
        "",
        f"**Layer**: {result.get('layer', '')}",
        "",
    ]
    flags = result.get("flags", [])
    if flags:
        lines += [f"**Flags**: {', '.join(flags)}", ""]
    if result.get("mode"):
        lines += [f"**Mode**: {result['mode']}", ""]
    if result.get("python_log_name"):
        lines += [f"**Python log**: `{result['python_log_name']}`", ""]
    evidence = result.get("evidence", [])
    if evidence:
        lines += ["## Evidence", "", "```"]
        lines += evidence
        lines += ["```", ""]
    if result.get("next_action"):
        lines += ["## Next action", "", result["next_action"], ""]
    return "\n".join(lines)
