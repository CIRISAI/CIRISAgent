"""Every WARN/ERROR a mesh run logged, grouped so each kind can be explained.

    python -m tools.qa_runner.local_mesh.log_audit <MESH_OUT> [--top N]

Reads each node's agent logs (`ciris_agent_*.log`) and node logs
(`ciris-server.log.*`), strips ANSI and timestamps, collapses ids, hashes,
numbers and quoted values into placeholders, and prints one row per distinct
(level, source, message shape) with its count per node. A shape that nobody can
explain is a finding, not noise.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

ANSI = re.compile(r"\x1b\[[0-9;]*m")
# ciris-server (tracing):  2026-10-28T21:07:02.921338Z  WARN target: message
RUST = re.compile(r"^\S+Z\s+(WARN|ERROR)\s+(?:\S+\{[^}]*\}:\s*)*([\w:]+):\s*(.*)$")
# agent (logging):          2026-10-28 21:00:13.906 - module - WARNING - message
PY = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+ - ([\w.]+) - (WARNING|ERROR|CRITICAL) - (.*)$")

_COLLAPSE = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{16,}\b"), "<hex>"),
    (re.compile(r"chat:pair:v1:<hex>"), "<room>"),
    (re.compile(r"\b(?:qa-node|ciris-node-bootstrap|ciris-agent-bootstrap|qa-runner-ciris-agent|ciris-canonical-\d|"
                r"ciris-gate-\w+|bench|ciris-client)-[\w-]+"), "<key>"),
    (re.compile(r"\"[^\"]{0,200}\""), "\"…\""),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s)?\b"), "<n>"),
]


def shape(message: str, width: int = 170) -> str:
    out = message
    for rx, repl in _COLLAPSE:
        out = rx.sub(repl, out)
    return out[:width]


def parse(line: str) -> Optional[Tuple[str, str, str]]:
    line = ANSI.sub("", line.rstrip("\n"))
    m = RUST.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = PY.match(line)
    if m:
        level = "WARN" if m.group(2) == "WARNING" else m.group(2)
        return level, m.group(1).rsplit(".", 1)[-1], m.group(3)
    return None


def node_files(home: Path) -> Iterable[Path]:
    logs = home / "ciris" / "logs"
    yield from sorted(logs.glob("ciris_agent_*.log"))
    yield from sorted(logs.glob("ciris-server.log.*"))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mesh_out", type=Path)
    ap.add_argument("--top", type=int, default=200)
    args = ap.parse_args(argv)

    nodes = sorted(p.name for p in args.mesh_out.iterdir() if (p / "ciris" / "logs").is_dir())
    counts: Dict[Tuple[str, str, str], Counter] = defaultdict(Counter)
    for node in nodes:
        for f in node_files(args.mesh_out / node):
            for line in f.open(errors="replace"):
                parsed = parse(line)
                if parsed:
                    level, src, msg = parsed
                    counts[(level, src, shape(msg))][node] += 1

    order = {"CRITICAL": 0, "ERROR": 1, "WARN": 2}
    rows = sorted(counts.items(), key=lambda kv: (order.get(kv[0][0], 9), -sum(kv[1].values())))
    print(f"{len(rows)} distinct WARN/ERROR shapes across {', '.join(nodes)}")
    for (level, src, msg), per in rows[: args.top]:
        tally = " ".join(f"{n}={per[n]}" for n in nodes)
        print(f"{level:8} {tally:24} {src[:34]:34} {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
