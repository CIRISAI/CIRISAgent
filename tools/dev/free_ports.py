#!/usr/bin/env python3
"""Free a set of TCP ports and PROVE they are free, on every platform we gate on.

WHY THIS EXISTS. The five-platform gate tore down between legs with

    pids=$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)

`lsof` does not exist on Windows Git Bash. Every probe failed into the `|| true`,
`pids` was always empty, `held` was always empty, and the workflow printed

    post-reset: 4242/4243/8080 free after 2s

having checked nothing at all. In run #34147279506 the node from the run-without-AI
leg was still holding :4242 when that line printed, and the next backend died with

    ReticulumTransport::new: reticulum node start: I/O error:
    Only one usage of each socket address ... (os error 10048)

which reads as a product fault and is not one. `platform_procs.pids_listening_on`
already handled Windows via `netstat -ano`; the YAML simply never used it.

ABSENCE OF A PID IS NOT PROOF OF A FREE PORT — that is the trap the old code fell
into, and `pids_listening_on` says so in its own docstring: empty means "could not
tell". So the authority here is not a process listing at all. It is a **bind
attempt**: if we can bind the port, it is free, and no amount of missing tooling
can make that answer wrong. The process listing is used only to find something to
kill and to name the culprit in a failure.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.qa_runner.platform_procs import kill_pids, pids_listening_on  # noqa: E402


def bindable(port: int) -> bool:
    """Can we bind `port`? The definitive answer, and the only one we trust.

    Both addresses are tried because a listener on either shape blocks the other:
    binding 0.0.0.0 fails while 127.0.0.1 is held, and vice versa. SO_REUSEADDR is
    deliberately NOT set — it would let the bind succeed against a socket in
    TIME_WAIT and hand back a false "free".
    """
    for host in ("127.0.0.1", "0.0.0.0"):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
        except OSError:
            return False
        finally:
            s.close()
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ports", nargs="+", type=int)
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for release")
    ap.add_argument("--label", default="teardown", help="prefix for log lines")
    args = ap.parse_args()

    for port in args.ports:
        pids = pids_listening_on(port)
        if pids:
            print(f"  {args.label}: freeing {port} ({', '.join(map(str, pids))})")
            kill_pids(pids)

    deadline = time.monotonic() + args.timeout
    held: list[int] = []
    while True:
        held = [p for p in args.ports if not bindable(p)]
        if not held or time.monotonic() >= deadline:
            break
        time.sleep(1.0)

    if not held:
        print(f"  {args.label}: {', '.join(map(str, args.ports))} verified free (bind test)")
        return 0

    print(f"  {args.label}: STILL HELD after {args.timeout:.0f}s: {', '.join(map(str, held))}")
    for port in held:
        pids = pids_listening_on(port)
        print(f"    :{port} -> {'pids ' + ', '.join(map(str, pids)) if pids else 'holder unknown (no process listing available)'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
