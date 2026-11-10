"""Did two nodes go direct, both ways, and only after they accepted each other?

    python -m tools.qa_runner.check_direct_links <logs-a> <logs-b>     # exit 1 on failure

Reads each node's log directory after a cross-NAT run (cross-nat-pair.yml) and
requires one link that BOTH sides report as punched, established after that side's
contact was accepted, with no ChannelExhausted and no stall-guard close. One side
ESTABLISHED and the other not is the one-sided move that stranded a live chat.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ESTABLISHED = re.compile(r"direct link ESTABLISHED|direct link: established, link moved onto the direct interface")
LINK = re.compile(r"\blink=\"?([0-9a-f]{16,})")
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
#: The requester logs mutual; the side that accepts logs accept.
ACCEPTED = re.compile(r"CONTACT (?:accept|mutual)\b")
LOST = "direct link LOST"
STALL = "CIRISEdge#926"
EXHAUSTED = re.compile(r"ChannelExhausted|channel-exhausted")


@dataclass
class NodeView:
    established: Dict[str, str] = field(default_factory=dict)
    first_accepted: str = ""
    lost: List[str] = field(default_factory=list)
    stalls: List[str] = field(default_factory=list)
    exhausted: List[str] = field(default_factory=list)
    last_seen: str = ""


def read_node(lines: Iterable[str]) -> NodeView:
    view = NodeView()
    for raw in lines:
        line = ANSI.sub("", raw)
        when = TIME.search(line)
        stamp = when.group(0) if when else ""
        # The line's own time: a line can also quote a later one, such as an expiry.
        own = TIME.match(line)
        view.last_seen = max(view.last_seen, own.group(0) if own else "")
        if ACCEPTED.search(line) and not view.first_accepted:
            view.first_accepted = stamp
        if ESTABLISHED.search(line):
            found = LINK.search(line)
            if found:
                view.established.setdefault(found.group(1), stamp)
        if LOST in line:
            view.lost.append(line.strip()[:200])
        if STALL in line:
            view.stalls.append(line.strip()[:200])
        if EXHAUSTED.search(line):
            view.exhausted.append(line.strip()[:200])
    return view


def verdict(a: NodeView, b: NodeView) -> List[str]:
    """What's wrong; empty means the direct link is proven."""
    problems: List[str] = []
    shared = sorted(set(a.established) & set(b.established))
    # A good retry doesn't excuse an earlier attempt: while one side is direct and the
    # other relayed, the link can strand a live chat.
    one_sided = sorted(set(a.established) ^ set(b.established))
    if one_sided:
        problems.append(f"one-sided move: {one_sided} established on one side only")
    elif not shared:
        problems.append("no direct link established")
    for link in shared:
        for name, view in (("a", a), ("b", b)):
            if not view.first_accepted or view.established[link] < view.first_accepted:
                problems.append(f"node {name} went direct on {link} before the contact was accepted")
    for name, view, other in (("a", a, b), ("b", b, a)):
        # A link does go down when its peer's job ends and the node stops. Only a loss
        # while the other side was still running counts.
        live = [x for x in view.lost + view.exhausted + view.stalls if _while_running(x, other)]
        problems += [f"node {name} ChannelExhausted: {x}" for x in view.exhausted[:3] if x in live]
        problems += [f"node {name} stall-guard close: {x}" for x in view.stalls[:3] if x in live]
        problems += [f"node {name} lost the direct link: {x}" for x in view.lost[:3] if x in live]
    return problems


def _while_running(line: str, other: NodeView) -> bool:
    found = TIME.search(line)
    return not found or not other.last_seen or found.group(0) <= other.last_seen


def log_lines(directory: Path) -> Iterable[str]:
    for path in sorted(directory.glob("ciris-server.log.*")) + sorted(directory.glob("ciris_agent_*.log")):
        yield from path.read_text(encoding="utf-8", errors="replace").splitlines()


def main(argv: Sequence[str]) -> int:
    a, b = (read_node(log_lines(Path(d))) for d in argv[:2])
    for name, view in (("a", a), ("b", b)):
        print(f"node {name}: accepted {view.first_accepted or 'never'}; established {view.established or 'none'}")
    problems = verdict(a, b)
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        print("PASS: both sides on one punched link, after acceptance, no exhaustion or stall")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
