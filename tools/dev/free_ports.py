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


def bindable_reuse(port: int) -> bool:
    """Can we bind `port` WITH ``SO_REUSEADDR`` — i.e. can the next server bind it?

    `bindable()` above deliberately refuses SO_REUSEADDR so a socket in TIME_WAIT
    cannot read as free. That is the right strictness for "is the previous backend
    gone", and the wrong answer for "can the next one start": every server we run
    (uvicorn, the ciris-server node) sets SO_REUSEADDR itself, so a port whose only
    obstruction is TIME_WAIT is available to them.

    The two answers together are what distinguishes the two states, and the
    distinction is not academic -- it cost the android leg of run 34291675402.
    Killing the linux backend left :8080 and :4243 in TIME_WAIT for the kernel's
    60 s; the strict probe read them as held, no listener existed to name (the
    log said "holder unknown"), the 30 s window expired, and the guard skipped
    android as though a stale backend were still serving. Nothing was serving.
    """
    # LOOPBACK ONLY, and deliberately: this probe answers "can the next server
    # bind", and every server we start here binds 127.0.0.1 (uvicorn on :8080,
    # the node's read API on :4243). The wildcard is NOT probed because a
    # loopback socket in TIME_WAIT refuses a 0.0.0.0 bind even with
    # SO_REUSEADDR, which would put us straight back to failing on residue.
    # A LIVE listener still fails this probe -- SO_REUSEADDR does not permit a
    # second listener on an overlapping address -- so the guard keeps its teeth.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
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

    deadline = time.monotonic() + args.timeout
    held: list[int] = []
    while True:
        # KILL ON EVERY PASS, not once at the start. The desktop client supervises
        # its backend and revives it (`[backend] reviving, attempt N/5`), so a
        # single kill can be undone a second later by a process that was not in
        # the first listing.
        for port in args.ports:
            pids = pids_listening_on(port)
            if pids:
                print(f"  {args.label}: freeing {port} ({', '.join(map(str, pids))})")
                kill_pids(pids)
        held = [p for p in args.ports if not bindable(p)]
        if not held or time.monotonic() >= deadline:
            break
        time.sleep(1.0)

    if not held:
        print(f"  {args.label}: {', '.join(map(str, args.ports))} verified free (bind test)")
        return 0

    # STRICTLY HELD IS NOT THE SAME AS OCCUPIED. Separate the two before failing:
    # a port with no listener that a SO_REUSEADDR bind accepts is TIME_WAIT
    # residue from the backend we just killed, and the next server -- which sets
    # SO_REUSEADDR -- will bind it. Failing on that is how a clean teardown was
    # reported as "a stale backend is still serving".
    listening = [p for p in held if pids_listening_on(p) or not bindable_reuse(p)]
    draining = [p for p in held if p not in listening]
    if draining:
        print(
            f"  {args.label}: {', '.join(map(str, draining))} in TIME_WAIT (no listener; SO_REUSEADDR bind "
            "accepted) -- the next server will bind these"
        )
    if not listening:
        return 0

    print(f"  {args.label}: STILL HELD after {args.timeout:.0f}s: {', '.join(map(str, listening))}")
    for port in listening:
        pids = pids_listening_on(port)
        print(f"    :{port} -> {'pids ' + ', '.join(map(str, pids)) if pids else 'holder unknown (no process listing available)'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
