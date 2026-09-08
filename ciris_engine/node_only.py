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
helpers a bare ``ciris-server`` command uses.

TROUBLESHOOTING. Every decision and hand-off is announced on stdout and the
``ciris.node_only`` logger with the prefix ``[RUN-WITHOUT-AI]``: where the
flag came from (which file, or the environment), the home and key alias in
use, the exact node command, where the node's own logs are, the health wait,
the client URL, and every exit code. ``grep RUN-WITHOUT-AI`` is the whole
story. The environment always wins over the file: ``CIRIS_RUN_WITHOUT_AI=false``
in the process environment re-enables the brain for one run without touching
the wizard's choice (a QA harness, an operator debugging a node).
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, NoReturn, Optional

ENV_FLAG = "CIRIS_RUN_WITHOUT_AI"
ENV_KEY_ID = "CIRIS_NODE_KEY_ID"
NODE_PORT = 4243
PREFIX = "[RUN-WITHOUT-AI]"
#: The truthy spellings, IDENTICAL on both sides of the wire on purpose. The
#: client parses this same key out of the same file (CIRISClient 0.5.203,
#: CIRISAgent#1151) and the two must never disagree about what "true" looks
#: like: a value one side accepts and the other does not sends the agent to one
#: port and the client to the other, which presents as a dead app. This is also
#: what `CIRIS_SERVICES_DISABLED` has always accepted (service_initializer.py,
#: llm_providers.py) -- one convention, three readers.
_TRUE = ("true", "1", "yes")
_FALSE = ("false", "0", "no")

logger = logging.getLogger("ciris.node_only")


def _say(msg: str, *, error: bool = False) -> None:
    """One line, two places: the console the launcher runs in, and the logger."""
    line = f"{PREFIX} {msg}"
    print(line, file=sys.stderr if error else sys.stdout, flush=True)
    (logger.error if error else logger.info)(line)


@dataclass(frozen=True)
class NodeOnlyConfig:
    home: str
    key_id: Optional[str]
    #: Where the decision came from, for the log: "environment" or the .env path.
    source: str = "environment"

    def node_args(self) -> List[str]:
        args = ["--home", self.home]
        if self.key_id:
            args += ["--key-id", self.key_id]
        return args

    @property
    def server_url(self) -> str:
        return f"http://localhost:{NODE_PORT}"

    @property
    def node_log_dir(self) -> str:
        return os.path.join(self.home, "logs")

    def describe(self) -> str:
        key = self.key_id or "NONE -> the wheel's default label; this is a DIFFERENT node identity than the wizard claimed"
        return f"home={self.home} key_id={key} decided_by={self.source} node_logs={self.node_log_dir}"


def ciris_home() -> str:
    """The home the wizard wrote to: managed ``/app``, ``$CIRIS_HOME``, a source
    checkout's cwd, else ``~/ciris``.

    Mirrors ``path_resolution.get_ciris_home()`` (same precedence, including its
    dev-mode rule: a ``.git`` in the cwd makes the checkout the home) and the
    wheel's ``_default_user_home()`` without importing either -- this runs before
    the CLI decides whether to import the engine at all. Diverging from the
    wizard here is not a cosmetic bug: the wizard writes the flag where IT
    resolves, and a resolver that looks elsewhere launches the desktop shell
    against an :8080 that its own child then abandons for :4243.
    """
    if os.path.isdir("/app/agent") or os.path.isdir("/app/.ciris_manager"):
        return "/app"
    env = os.environ.get("CIRIS_HOME")
    if env:
        return os.path.expanduser(env)
    if "ANDROID_DATA" not in os.environ and os.path.isdir(os.path.join(os.getcwd(), ".git")):
        return os.getcwd()
    return os.path.join(os.path.expanduser("~"), "ciris")


def env_file_path(home: str) -> str:
    """Where the wizard put ``.env``: ``$CIRIS_CONFIG_DIR/.env`` when that override
    is set (``first_run.get_default_config_path`` honours it first), else ``<home>/.env``.
    """
    override = os.environ.get("CIRIS_CONFIG_DIR")
    if override:
        return os.path.join(os.path.expanduser(override), ".env")
    return os.path.join(home, ".env")


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
    """The node-only configuration when the owner chose to run without AI, else None.

    Quiet when the answer is "no" and nothing asked for it; says why when the
    file asked for it but the environment vetoed, and says everything when the
    answer is "yes".
    """
    home = home or ciris_home()
    env_path = env_file_path(home)
    file_values = read_env_file(env_path)
    env_flag = os.environ.get(ENV_FLAG, "").strip().lower()
    file_flag = file_values.get(ENV_FLAG, "").strip().lower()
    if env_flag in _FALSE:
        if file_flag in _TRUE:
            _say(f"{ENV_FLAG}=false in the environment overrides {env_path} ({ENV_FLAG}=true) -- running the agent runtime for this one run")
            _warn_client_will_disagree(env_path, agent_port=8080, client_port=NODE_PORT)
        return None
    if env_flag in _TRUE:
        source = "environment"
        if file_flag not in _TRUE:
            _say(f"{ENV_FLAG}=true comes from the environment, not {env_path}")
            _warn_client_will_disagree(env_path, agent_port=NODE_PORT, client_port=8080)
    elif file_flag in _TRUE:
        source = env_path
    else:
        return None
    key_id = os.environ.get(ENV_KEY_ID) or file_values.get(ENV_KEY_ID) or None
    cfg = NodeOnlyConfig(home=home, key_id=(key_id.strip() if key_id else None), source=source)
    _say(f"the owner chose to run without AI: this process is ciris-server and the client, nothing else ({cfg.describe()})")
    if not cfg.key_id:
        _say(
            f"no {ENV_KEY_ID} in {env_path} or the environment: the node will boot on the wheel's default key label, "
            "which is NOT the identity the wizard claimed. Set it to the node's keystore alias to fix.",
            error=True,
        )
    return cfg


def _warn_client_will_disagree(env_path: str, *, agent_port: int, client_port: int) -> None:
    """The environment override desynchronizes the client, in EITHER direction.

    The client decides its endpoint by reading ``CIRIS_RUN_WITHOUT_AI`` from
    this same file (CIRISClient 0.5.203) -- it cannot see this process's
    environment. So an environment value that disagrees with the file puts the
    two on different ports, and the app shows a spinner against a port nothing
    is listening on. That makes this override a HEADLESS affordance: fine for
    ``ciris-agent --server`` or a QA harness, wrong whenever a client is
    watching. Said loudly rather than discovered on a device.
    """
    _say(
        f"the environment disagrees with {env_path}: this process will serve :{agent_port}, but a client reading "
        f"that file will look for :{client_port} and find nothing. Use this override only with no client attached "
        f"(`ciris-agent --server`, QA); to change it for real, edit {ENV_FLAG} in the file.",
        error=True,
    )


def node_command(cfg: NodeOnlyConfig) -> List[str]:
    """The headless node as a child-process command line (what ``exec`` and the launcher use)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--headless", *cfg.node_args()]
    return [sys.executable, "-m", "ciris_server", "--headless", *cfg.node_args()]


def _wheel_or_die() -> None:
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]  # noqa: F401
    except ImportError as exc:
        _say(
            f"the ciris-server wheel is not importable ({exc}). Run without AI needs it: `pip install ciris-server`. "
            f"Or set {ENV_FLAG}=false in the environment to run the brain instead.",
            error=True,
        )
        raise SystemExit(2) from exc


def run_headless(cfg: NodeOnlyConfig) -> NoReturn:
    """Serve the node in THIS process and never return (``--server`` mode, and mobile)."""
    _wheel_or_die()
    sys.argv = ["ciris-server", "--headless", *cfg.node_args()]
    _say(f"serving the node in-process (pid={os.getpid()}): argv={sys.argv} read API={cfg.server_url}")
    from ciris_server.cli import main as node_main  # type: ignore[import-not-found, import-untyped, unused-ignore]

    try:
        node_main()
    except SystemExit as exc:
        _say(f"node exited with code {exc.code}")
        raise
    except Exception as exc:  # noqa: BLE001 -- name it before dying
        _say(f"node crashed: {type(exc).__name__}: {exc} -- see {cfg.node_log_dir}", error=True)
        raise
    _say("node returned; exiting 0")
    raise SystemExit(0)


def exec_into_node(cfg: NodeOnlyConfig) -> bool:
    """Replace this process with the headless node (the post-setup restart).

    The wizard ran on the brain; the owner chose no AI; the brain is done. The
    same pid keeps serving so a launcher waiting on it (``ciris-agent``) sees
    one process, and the node's read API comes up on :4243. Returns False if
    the exec itself failed (the caller then exits normally and the NEXT boot
    hands off instead); on success it never returns.
    """
    # NOT INSIDE AN EMBEDDED RUNTIME -- AND NOT BY EXITING EITHER. On Android
    # (Chaquopy) and iOS (BeeWare) this Python is a thread of the host app and
    # sys.executable is the host's own binary; on Android, /system/bin/app_process64.
    # execv of that with `-m ciris_server` is not a Python invocation: it REPLACED
    # the app's process image, the app died, and Android's foreground-service
    # restart brought it back (run #34165538262, pids 5883 -> 6241). It worked as
    # a crash. The first correction -- exit deliberately and let the host restart
    # us -- is WORSE on iOS, where exit(0) is the app vanishing mid-setup with no
    # relaunch (CIRISClient#43). And the host cannot restart the interpreter
    # either: Chaquopy initialises CPython once per process, so a service-level
    # restart would re-enter mobile_main in an interpreter still holding this
    # runtime's loop, threads and Edge transport -- CIRISAgent#1152's shape.
    #
    # So the agent never ends a process it does not own, on any platform. Here
    # it records nothing new (the flag is already in the home's .env), :8080 has
    # been told to stop, and it RETURNS. The next boot serves the node in-process
    # from the recorded flag (main.py -> run_headless). Serving it in-process in
    # THIS session -- the client's preferred shape (1) -- is gated on the parked
    # runtime actually releasing Edge and persist on shutdown, which is #1152.
    from ciris_engine.logic.utils.platform_detection import get_platform_name, is_desktop

    if not is_desktop():
        _say(
            f"embedded runtime ({get_platform_name()}): this Python is the host app's, so there is no process "
            f"to exec into and none to exit. :8080 has stopped and the flag is recorded; the node serves "
            f"{cfg.server_url} from the NEXT boot of the runtime (main.py reads the flag). In-session hand-off "
            f"on this platform is gated on the parked runtime releasing Edge/persist (CIRISAgent#1152)."
        )
        return False

    cmd = node_command(cfg)
    _say(f"replacing this process (pid={os.getpid()}) with the node in place: {cmd} -- the read API comes up on {cfg.server_url}; node logs in {cfg.node_log_dir}")
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execv(cmd[0], cmd)
    except OSError as exc:
        _say(f"exec failed ({exc}); exiting normally -- the next boot will start the node from the recorded flag", error=True)
        return False
    return True  # pragma: no cover -- execv does not return


def run_desktop(cfg: NodeOnlyConfig) -> int:
    """Start the node as a child, wait for its read API, launch the client, tear down.

    The wheel's own desktop mode does exactly this with ITS default home and
    key label; here the home and key alias are the wizard's, so the node the
    client opens is the node the owner claimed.
    """
    import subprocess
    import time

    _wheel_or_die()
    from ciris_server.cli import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        _spawn_headless_node,
        _wait_for_node_health,
    )

    _say(f"starting the node as a child: {node_command(cfg)}")
    node_proc = _spawn_headless_node(cfg.node_args())
    _say(f"node pid={node_proc.pid}; node logs in {cfg.node_log_dir}")
    time.sleep(2.0)
    early = node_proc.poll()
    if early is not None:
        _say(f"node exited with code {early} within 2s of starting -- see {cfg.node_log_dir} (usual causes: {NODE_PORT - 1}/{NODE_PORT} already bound, unreadable home, missing key material)", error=True)
        return early if early != 0 else 1
    try:
        _say(f"waiting for the node's read API at {cfg.server_url}/health (60s)")
        if _wait_for_node_health(cfg.server_url, node_proc, timeout=60.0):
            _say("node read API is up")
        else:
            late = node_proc.poll()
            if late is not None:
                _say(f"node exited with code {late} while waiting for its read API -- see {cfg.node_log_dir}", error=True)
                return late if late != 0 else 1
            _say("node not answering health checks after 60s; launching the client anyway, it will retry", error=True)
        from ciris_server.desktop_launcher import launch_desktop_app  # type: ignore[import-not-found, import-untyped, unused-ignore]

        _say(f"launching the desktop client against {cfg.server_url} (CIRIS_API_URL)")
        rc = int(launch_desktop_app(server_url=cfg.server_url))
        _say(f"desktop client exited with code {rc}")
        return rc
    finally:
        _say(f"stopping the node (pid={node_proc.pid})")
        node_proc.terminate()
        try:
            node_proc.wait(timeout=10)
            _say("node stopped")
        except subprocess.TimeoutExpired:
            node_proc.kill()
            _say("node did not stop within 10s; killed", error=True)
