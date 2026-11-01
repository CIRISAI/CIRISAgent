"""Install the substrate's Rust `tracing` subscriber so its logs stop vanishing.

#937. The report's core symptom was "the log did not advance by a single
line for 15 minutes" while the agent sat blocked in persist's migration
phase. persist was not silent — it emits

    tracing::info!(lock_id = …, "ciris-persist: migration phase begin \
                                 (advisory lock acquired)")

at `src/store/postgres.rs:1181`, plus a matching "migration phase complete".
Those lines went nowhere because a Rust `tracing` event reaches a sink only
if some subscriber is installed, and a Python host that never calls
`init_tracing()` installs none. Every substrate log — persist, edge, server
— was being discarded at the source.

## What this is, and what it deliberately is not

The substrate exposes `init_tracing(log_dir=None, filter=None)`, which
installs a `tracing_subscriber` writing to **stdout** (and, given
`log_dir`, a daily `ciris-server.log` file sink). It is not a `pyo3_log`
style bridge: there is no hook that forwards Rust events into Python's
`logging` module, so substrate output does NOT pass through Python
handlers and cannot be re-levelled by `logging` configuration.

That boundary is load-bearing for incident hygiene (#935). The incident
capture handler is attached to the Python ROOT logger and promotes every
WARNING/ERROR to `incidents_latest.log`
(`logging_config.py:150-160`). Because substrate events never enter
Python `logging` at all, a chatty Rust subsystem structurally cannot
flood the incident log — the isolation is by construction, not by
filter tuning. The tests assert this property directly.

The cost of that same boundary is that substrate logs land on stdout
rather than in `latest.log`. Passing `log_dir` recovers most of it: the
substrate writes its own file next to ours, so an operator collecting
`logs/` gets both halves.

## Filter policy

`warn` globally with `info` for the three substrate crates. A blanket
`info` would open the Reticulum/edge networking firehose; `warn` alone
would drop the migration-phase lines this issue exists to recover. If the
operator has set `RUST_LOG` we pass `filter=None` and let the env win,
since the substrate's own docstring documents `filter` as overriding it.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Explicit override, highest precedence (e.g. "info,ciris_edge=debug").
SUBSTRATE_LOG_FILTER_ENV = "CIRIS_SUBSTRATE_LOG"

# Kill switch: set truthy to leave the substrate silent.
SUBSTRATE_TRACING_DISABLED_ENV = "CIRIS_SUBSTRATE_TRACING_DISABLED"

# Quiet by default, except the crates whose boot-phase logging we need.
# `ciris_persist` is the one that carries the #937 migration-phase lines.
DEFAULT_SUBSTRATE_LOG_FILTER = (
    "warn,ciris_persist=info,ciris_server=info,ciris_edge=info"
)

_installed = False


def substrate_tracing_installed() -> bool:
    """Whether this process has already installed the substrate subscriber."""
    return _installed


def reset_substrate_tracing_state() -> None:
    """Test seam — clear the module's installed flag.

    Note this cannot uninstall the Rust subscriber (that is a process-global
    `try_init` with no teardown); it only resets our bookkeeping.
    """
    global _installed
    _installed = False


#: Logger the substrate's records arrive on in python_logging mode
#: (`ciris_node.<crate>`, e.g. `ciris_node.ciris_edge`).
SUBSTRATE_PYTHON_LOGGER = "ciris_node"

#: `file` keeps the substrate's own daily `ciris-server.log.<date>` sink.
SUBSTRATE_LOG_SINK_ENV = "CIRIS_SUBSTRATE_LOG_SINK"


def call_init_tracing(init_tracing: Any, log_dir: Optional[str], log_filter: Optional[str]) -> Any:
    """Call the substrate's `init_tracing`, preferring ONE log file.

    ciris-server 0.5.243 can emit the node's tracing as Python records on
    `ciris_node.<crate>`, so they land in OUR latest.log under OUR rotation
    instead of a second `ciris-server.log.<date>` file. An older wheel rejects
    the `python_logging` kwarg (TypeError) and keeps its file sink at
    `log_dir`; `CIRIS_SUBSTRATE_LOG_SINK=file` keeps it on purpose. The
    records never reach incidents_latest.log: the incident handler drops
    `ciris_node.*` (#935).
    """
    if os.environ.get(SUBSTRATE_LOG_SINK_ENV, "").strip().lower() != "file":
        try:
            return init_tracing(filter=log_filter, python_logging=True)
        except TypeError:
            pass  # pre-0.5.243: no python_logging sink
    return init_tracing(log_dir=log_dir, filter=log_filter)


def is_substrate_record(record: logging.LogRecord) -> bool:
    """A record the substrate emitted through Python logging (python_logging sink)."""
    name = record.name
    return name == SUBSTRATE_PYTHON_LOGGER or name.startswith(SUBSTRATE_PYTHON_LOGGER + ".")


def resolve_substrate_log_filter() -> Optional[str]:
    """Pick the `EnvFilter` string to hand the substrate.

    Returns `None` to mean "defer to `RUST_LOG`", which is what the
    substrate does when `filter` is omitted.
    """
    explicit = os.environ.get(SUBSTRATE_LOG_FILTER_ENV, "").strip()
    if explicit:
        return explicit
    if os.environ.get("RUST_LOG", "").strip():
        # Operator has spoken through the standard Rust channel — don't
        # override it. The substrate's `filter` arg beats the env var.
        return None
    return DEFAULT_SUBSTRATE_LOG_FILTER


def install_substrate_tracing(
    log_dir: Optional[str] = None, force: bool = False
) -> bool:
    """Install the substrate tracing subscriber. Returns True if we installed.

    Contract, in priority order:

    * **Never fails boot.** A substrate without the entry point, or an
      entry point that raises, logs once and returns False. Losing logs is
      bad; refusing to start because logging is unavailable is worse.
    * **Idempotent.** Safe to call from several boot paths. The substrate's
      own `try_init` is idempotent too, so a double call is harmless even
      across module reloads.
    * **Inert under pytest** unless `force=True`, so a process-global
      stdout subscriber does not attach itself to every test run.

    Args:
        log_dir: agent log directory. When given, the substrate also writes
            `<log_dir>/ciris-server.log` so its output sits beside ours.
        force: install even under pytest.
    """
    global _installed

    if _installed:
        return False

    if os.environ.get(SUBSTRATE_TRACING_DISABLED_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        logger.debug(
            "Substrate tracing disabled via %s", SUBSTRATE_TRACING_DISABLED_ENV
        )
        return False

    if os.environ.get("PYTEST_CURRENT_TEST") and not force:
        return False

    try:
        from ciris_engine.logic.persistence._substrate import (  # one-wheel seam (#896)
            init_tracing,
        )
    except ImportError as e:
        logger.warning(
            "Substrate tracing unavailable (%s) — persist/edge logs will not be "
            "captured. This does not block startup.",
            e,
        )
        return False

    if init_tracing is None:
        logger.warning(
            "Substrate build exposes no init_tracing() — persist/edge logs will "
            "not be captured. This does not block startup."
        )
        return False

    log_filter = resolve_substrate_log_filter()
    try:
        # Both kwargs are optional on the substrate side; pass them
        # explicitly so a None filter means "defer to RUST_LOG".
        call_init_tracing(init_tracing, log_dir, log_filter)
    except Exception as e:  # noqa: BLE001 - logging must never block boot
        logger.warning(
            "Substrate tracing init failed (%s) — persist/edge logs will not be "
            "captured. This does not block startup.",
            e,
        )
        return False

    _installed = True
    logger.info(
        "Substrate tracing installed (filter=%s, log_dir=%s). persist/edge logs "
        "go to stdout%s — they do NOT pass through Python logging, so they "
        "cannot reach incidents_latest.log.",
        log_filter or f"$RUST_LOG={os.environ.get('RUST_LOG', '')}",
        log_dir or "<none>",
        f" and {log_dir}/ciris-server.log" if log_dir else "",
    )
    return True


#: The name this process carries in ps/top/pgrep (Linux keeps 15 bytes).
PROCESS_LABEL = "ciris-agent"


def set_process_label(label: str = PROCESS_LABEL) -> bool:
    """Name this process and the node's runtime threads (ciris-server 0.5.243).

    So `pgrep ciris-agent` finds an agent when several nodes run on one host.
    Desktop/server only: an embedded app (Android, iOS) is the host's process
    and its name is the host's, so we leave it alone. Call early, from the main
    thread, before the node serves. Never fails boot; False when skipped.
    """
    try:
        from ciris_engine.logic.utils.path_resolution import is_android, is_ios

        if is_android() or is_ios():
            return False
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        fn = getattr(ciris_server, "set_process_label", None) or getattr(
            getattr(ciris_server, "_native", None), "set_process_label", None
        )
        if fn is None:
            return False  # pre-0.5.243
        fn(label)
        return True
    except Exception as e:  # noqa: BLE001 - a process name must never block boot
        logger.debug("process label not set (%s)", e)
        return False
