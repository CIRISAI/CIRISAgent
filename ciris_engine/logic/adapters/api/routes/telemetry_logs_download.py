"""The owner's log download: agent and node logs as one zip.

WHY. On a phone the logs live inside the app sandbox, so a release build has
no way to reach them: no run-as, no file manager. The Logs screen showed parsed
entries and offered no way to take them off the device, and the client's debug
bundle carried only its own Kotlin buffer, which cannot explain anything the
agent or the node did. This is the one route that hands over the files
themselves.

WHAT. Everything under CIRIS_HOME/logs that is a log: the agent's
(ciris_agent_*.log, latest.log, incidents_*.log) and the node's
(ciris-server.log*, written by the substrate's tracing sink into the same
directory). Each file is a TAIL, because a week of DEBUG is hundreds of MB, and
the whole zip is capped. Secrets are redacted line by line before anything
leaves the process. A MANIFEST.txt says what was included, what was cut and
why.

WHO. ADMIN, the node's owner. /v1/telemetry/logs stays OBSERVER and returns
parsed entries; raw files carry more than an observer should see.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

#: Per-file tail, default and bounds (KiB).
DEFAULT_TAIL_KIB = 2048
MAX_TAIL_KIB = 8192
#: The whole bundle, uncompressed. A phone can send this over any messenger.
MAX_TOTAL_BYTES = 16 * 1024 * 1024
#: Older files are not today's problem; bound the file count too.
MAX_AGE_SECONDS = 3 * 24 * 3600
MAX_FILES = 16
#: Below this much room left, a file is named as cut rather than shipped as a
#: few bytes of tail that read like the whole log.
MIN_FILE_ROOM = 1024

_LOG_NAME = re.compile(r"(\.log$|\.log\.)")

#: (pattern, replacement). Order matters: the specific key shapes run before
#: the generic `key=value` rule, so a matched key is never half-redacted.
_REDACTIONS: List[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=:\-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\bsess:[A-Za-z0-9._\-]+"), "sess:[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-[REDACTED]"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{16,}"), "gsk_[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "AIza[REDACTED]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|password|passwd|secret|client[_-]?secret)"
            r"(\"?\s*[:=]\s*\"?)([^\s\"',}&]+)"
        ),
        r"\1\2[REDACTED]",
    ),
]


def _size(n: int) -> str:
    return f"{n // (1024 * 1024)} MiB" if n >= 1024 * 1024 else f"{n // 1024} KiB" if n >= 1024 else f"{n} bytes"


def redact(line: str) -> str:
    """One line, with every secret shape this module knows replaced."""
    for pattern, replacement in _REDACTIONS:
        line = pattern.sub(replacement, line)
    return line


@dataclass
class BundledFile:
    name: str
    size: int
    included_bytes: int
    truncated: bool


@dataclass
class LogBundle:
    data: bytes
    files: List[BundledFile] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


def _candidates(logs_dir: Path, now: float) -> List[Path]:
    """Log files, newest first, each underlying file once (latest.log may link to another)."""
    if not logs_dir.is_dir():
        return []
    seen: set[Path] = set()
    out: List[Path] = []
    files = [p for p in logs_dir.iterdir() if p.is_file() and _LOG_NAME.search(p.name)]
    for p in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True):
        real = p.resolve()
        if real in seen or now - p.stat().st_mtime > MAX_AGE_SECONDS:
            continue
        seen.add(real)
        out.append(p)
    return out[:MAX_FILES]


def _tail(path: Path, max_bytes: int) -> tuple[bytes, int, bool]:
    """The last `max_bytes` of `path`, starting at a line boundary."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size <= max_bytes:
            return fh.read(), size, False
        fh.seek(size - max_bytes)
        chunk = fh.read()
    cut = chunk.find(b"\n")
    return (chunk[cut + 1 :] if cut >= 0 else chunk), size, True


def build_log_bundle(
    logs_dir: Path,
    tail_kib: int = DEFAULT_TAIL_KIB,
    versions: Optional[dict[str, str]] = None,
    now: Optional[float] = None,
) -> LogBundle:
    """The zip: each log's redacted tail, then MANIFEST.txt naming what is in it."""
    now = time.time() if now is None else now
    tail_bytes = max(1, min(tail_kib, MAX_TAIL_KIB)) * 1024
    buf = io.BytesIO()
    bundle = LogBundle(data=b"")
    total = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in _candidates(logs_dir, now):
            room = MAX_TOTAL_BYTES - total
            if room < MIN_FILE_ROOM:
                bundle.skipped.append(f"{path.name}: the bundle reached its {_size(MAX_TOTAL_BYTES)} cap")
                continue
            try:
                raw, size, truncated = _tail(path, min(tail_bytes, room))
            except OSError as exc:
                bundle.skipped.append(f"{path.name}: unreadable ({exc.__class__.__name__})")
                continue
            text = "".join(redact(line) for line in raw.decode("utf-8", errors="replace").splitlines(keepends=True))
            body = text.encode("utf-8")
            zf.writestr(path.name, body)
            total += len(body)
            bundle.files.append(BundledFile(path.name, size, len(body), truncated or len(raw) < size))
        zf.writestr("MANIFEST.txt", _manifest(logs_dir, bundle, tail_bytes, versions or {}))
    bundle.data = buf.getvalue()
    return bundle


def _manifest(logs_dir: Path, bundle: LogBundle, tail_bytes: int, versions: dict[str, str]) -> str:
    lines = [
        "CIRIS log bundle",
        f"captured: {datetime.now(timezone.utc).isoformat()}",
        *(f"{k}: {v}" for k, v in sorted(versions.items())),
        f"source: {logs_dir.name}/ (agent and node logs share this directory)",
        f"per-file tail: {_size(tail_bytes)}; bundle cap: {_size(MAX_TOTAL_BYTES)}; "
        f"files modified in the last {MAX_AGE_SECONDS // 3600} h",
        "secrets: bearer and session tokens, API keys and password/secret/token values are redacted",
        "",
        "files:",
    ]
    if not bundle.files:
        lines.append("  (none: no log files in the window)")
    for f in bundle.files:
        cut = f", last {f.included_bytes} of {f.size} bytes" if f.truncated else ""
        lines.append(f"  {f.name}{cut}")
    if bundle.skipped:
        lines += ["", "skipped:", *(f"  {s}" for s in bundle.skipped)]
    return "\n".join(lines) + "\n"
