"""Run without AI: the process is ciris-server and the client, nothing else.

The wizard's "Run without AI" choice (CIRISAgent#1149) is recorded at
setup-complete as ``CIRIS_RUN_WITHOUT_AI=true`` in the home's ``.env``, next
to the node's keystore alias (``CIRIS_NODE_KEY_ID``). On every boot after that,
each entry point asks this module FIRST -- before importing the engine -- and
if the flag is set it hands the process to the ``ciris-server`` wheel: the
node boots on the SAME home and key alias the wizard claimed, and the desktop
client is launched against the node's read API. No runtime, no API adapter, no
node fold, no LLM: zero CIRISAgent code beyond "start ciris-server and the
client".

This module therefore imports nothing from the engine. It reads one file and
calls into ``ciris_server.cli`` / ``ciris_server.desktop_launcher``, the same
helpers a bare ``ciris-server`` command uses (desktop-first launcher,
CIRISServer wheel >= 0.5.19x).

The environment always wins over the file: ``CIRIS_RUN_WITHOUT_AI=false`` in
the process environment re-enables the brain for one run without touching the
wizard's choice (a QA harness, an operator debugging a node).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, NoReturn, Optional

ENV_FLAG = "CIRIS_RUN_WITHOUT_AI"
ENV_KEY_ID = "CIRIS_NODE_KEY_ID"
NODE_PORT = 4243
_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")


@dataclass(frozen=True)
class NodeOnlyConfig:
    home: str
    key_id: Optional[str]

    def node_args(self) -> List[str]:
        args = ["--home", self.home]
        if self.key_id:
            args += ["--key-id", self.key_id]
        return args

    @property
    def server_url(self) -> str:
        return f"http://localhost:{NODE_PORT}"


def ciris_home() -> str:
    """The home the wizard wrote to: managed ``/app``, ``$CIRIS_HOME``, else ``~/ciris``.

    Mirrors ``path_resolution.get_ciris_home()`` and the wheel's
    ``_default_user_home()`` without importing either.
    """
    if os.path.isdir("/app/agent") or os.path.isdir("/app/.ciris_manager"):
        return "/app"
    env = os.environ.get("CIRIS_HOME")
    if env:
        return os.path.expanduser(env)
    return os.path.join(os.path.expanduser("~"), "ciris")


def read_env_file(path: str) -> Dict[str, str]:
    """``KEY=value`` lines, comments and blanks skipped, surrounding quotes stripped."""
    values: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if key:
                    values[key] = value
    except OSError:
        return {}
    return values


def node_only_config(home: Optional[str] = None) -> Optional[NodeOnlyConfig]:
    """The node-only configuration when the owner chose to run without AI, else None."""
    home = home or ciris_home()
    file_values = read_env_file(os.path.join(home, ".env"))
    env_flag = os.environ.get(ENV_FLAG, "").strip().lower()
    if env_flag in _FALSE:
        return None
    if env_flag not in _TRUE and file_values.get(ENV_FLAG, "").strip().lower() not in _TRUE:
        return None
    key_id = os.environ.get(ENV_KEY_ID) or file_values.get(ENV_KEY_ID) or None
    return NodeOnlyConfig(home=home, key_id=(key_id.strip() if key_id else None))


def node_command(cfg: NodeOnlyConfig) -> List[str]:
    """The headless node as a child-process command line (what ``exec`` and the launcher use)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--headless", *cfg.node_args()]
    return [sys.executable, "-m", "ciris_server", "--headless", *cfg.node_args()]


def run_headless(cfg: NodeOnlyConfig) -> NoReturn:
    """Serve the node in THIS process and never return (server mode, mobile)."""
    print(f"Run without AI: starting ciris-server node only (home={cfg.home}, key={cfg.key_id or 'default'})")
    sys.argv = ["ciris-server", "--headless", *cfg.node_args()]
    from ciris_server.cli import main as node_main  # type: ignore[import-not-found, import-untyped, unused-ignore]

    node_main()
    raise SystemExit(0)


def exec_into_node(cfg: NodeOnlyConfig) -> NoReturn:
    """Replace this process with the headless node (the post-setup restart).

    The wizard ran on the brain; the owner chose no AI; the brain is done. The
    same pid keeps serving so a launcher waiting on it (``ciris-agent``) sees
    one process, and the node's read API comes up on :4243.
    """
    cmd = node_command(cfg)
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(cmd[0], cmd)


def run_desktop(cfg: NodeOnlyConfig) -> int:
    """Start the node as a child, wait for its read API, launch the client, tear down.

    The wheel's own desktop mode does exactly this with ITS default home and
    key label; here the home and key alias are the wizard's, so the node the
    client opens is the node the owner claimed.
    """
    import subprocess
    import time

    from ciris_server.cli import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        _spawn_headless_node,
        _wait_for_node_health,
    )

    print(f"Run without AI: starting ciris-server node (home={cfg.home}, key={cfg.key_id or 'default'})...")
    node_proc = _spawn_headless_node(cfg.node_args())
    time.sleep(2.0)
    early = node_proc.poll()
    if early is not None:
        print(f"ERROR: ciris-server node exited with code {early} before serving", file=sys.stderr)
        return early if early != 0 else 1
    try:
        if not _wait_for_node_health(cfg.server_url, node_proc, timeout=60.0):
            late = node_proc.poll()
            if late is not None:
                print(f"ERROR: ciris-server node exited with code {late}", file=sys.stderr)
                return late if late != 0 else 1
            print("WARNING: node not answering health checks yet; launching the client anyway.")
        from ciris_server.desktop_launcher import launch_desktop_app  # type: ignore[import-not-found, import-untyped, unused-ignore]

        print("\nLaunching CIRIS Desktop (node only)...")
        return int(launch_desktop_app(server_url=cfg.server_url))
    finally:
        print("\nShutting down node...")
        node_proc.terminate()
        try:
            node_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            node_proc.kill()
