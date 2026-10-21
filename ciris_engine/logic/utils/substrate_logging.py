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
from typing import Optional

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
        init_tracing(log_dir=log_dir, filter=log_filter)
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
