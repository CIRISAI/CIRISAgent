"""Mock-LLM trace-export guard (CIRISAgent#1244).

Traces produced while the mock LLM answers are test fixtures, not reasoning.
From 2026-08-02 to about 2026-09-06, 1,499 of them reached the PRODUCTION
canonical/lens (all ``model='mock-model'``). 766 of those carried the mock's
whole LLM message array. This module is the ONE place that answers two
questions:

1. Is the mock LLM active in this process?  (:func:`is_mock_llm_active`)
2. May a trace leave this node for a given sink?  (:func:`remote_trace_export_permitted`)
3. What kind of run produced a trace?  (:func:`trace_run_kind`, CIRISAgent#1245)

The rule under the mock LLM is fixed: only the local tee
(``CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR``) and loopback endpoints
(127.0.0.0/8, ::1, ``localhost``) may receive traces. Every remote sink,
meaning federation replication to a canonical peer or a non-loopback lens
endpoint, is refused. Consent does not lift this and neither does config.
There is no override flag, by design ("No Bypass Patterns"): a mock run that
needs a remote sink is a mis-configured run.

Detection is deliberately redundant, because the call sites run at different
boot phases (edge init runs before the mock module loads):

* a one-way process latch, set by every mock entry point
  (``main.py --mock-llm``, ``check_mock_llm``, the module loader's
  ``MOCK_MODULE_LOADED`` path, ``MockLLMService.__init__``);
* ``CIRIS_MOCK_LLM`` truthy in the environment or the ``.env`` file;
* ``--mock-llm`` on the process command line.

The latch can never be cleared. Once the mock has answered anything in this
process, every later trace carries mock output.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import sys
import threading
from enum import Enum
from typing import Optional, Set
from urllib.parse import urlsplit

from ciris_engine.logic.utils.env_flags import TRUTHY

logger = logging.getLogger(__name__)

_MOCK_ENV_VAR = "CIRIS_MOCK_LLM"
_MOCK_CLI_FLAG = "--mock-llm"

_lock = threading.Lock()
_latched_source: Optional[str] = None
_refusals_logged: Set[str] = set()


def mark_mock_llm_active(source: str) -> None:
    """Record that the mock LLM is active in this process. One-way: never cleared."""
    global _latched_source
    with _lock:
        if _latched_source is None:
            _latched_source = source
            logger.info("[MOCK-GUARD] mock LLM active (source=%s) — remote trace export disabled", source)


def mock_llm_source() -> Optional[str]:
    """Why the mock LLM is considered active, or None when it is not."""
    if _latched_source is not None:
        return _latched_source
    if os.environ.get(_MOCK_ENV_VAR, "").strip().lower() in TRUTHY:
        return f"env:{_MOCK_ENV_VAR}"
    try:
        from ciris_engine.logic.config.env_utils import get_env_var

        if str(get_env_var(_MOCK_ENV_VAR, "") or "").strip().lower() in TRUTHY:
            return f".env:{_MOCK_ENV_VAR}"
    except Exception:  # noqa: BLE001 - config layer may not be importable this early
        pass
    if _MOCK_CLI_FLAG in sys.argv:
        return f"argv:{_MOCK_CLI_FLAG}"
    return None


def is_mock_llm_active() -> bool:
    """True when ANY mock-LLM signal is present (see the module docstring)."""
    return mock_llm_source() is not None


def is_loopback_endpoint(endpoint: Optional[str]) -> bool:
    """True only for a URL or ``host[:port]`` whose host is literally loopback.

    No DNS. A hostname other than ``localhost`` is never trusted to be local,
    because resolution is configuration and configuration is what failed here.
    """
    if not endpoint:
        return False
    raw = endpoint.strip()
    try:
        host = urlsplit(raw if "//" in raw else f"//{raw}").hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def remote_trace_export_permitted(sink: str, endpoint: Optional[str] = None) -> bool:
    """May traces go to ``sink``? Under the mock LLM only loopback is allowed.

    Args:
        sink: a short human name for the send path, used in the refusal log.
        endpoint: the sink's address when it has one. ``None`` means the
            destination is not locally constrained (for example federation
            replication to a canonical peer), and that is refused under the mock.

    Returns True when the mock is not active, or when ``endpoint`` is loopback.
    A refusal is logged once per sink at INFO.
    """
    source = mock_llm_source()
    if source is None:
        return True
    if is_loopback_endpoint(endpoint):
        return True
    with _lock:
        first = sink not in _refusals_logged
        _refusals_logged.add(sink)
    if first:
        logger.info(
            "[MOCK-GUARD] REFUSED remote trace export via %s (endpoint=%s): the mock LLM is active (%s). "
            "Mock traces may only reach the local tee or a loopback endpoint (CIRISAgent#1244). "
            "Consent and config cannot lift this.",
            sink,
            endpoint or "<remote mesh>",
            source,
        )
    return False


class TraceRunKind(str, Enum):
    """What kind of run produced a trace (CIRISAgent#1245).

    "Synthetic" is a bigger set than "mock LLM": the mental-health battery
    drives a REAL model, and its rows were indistinguishable from real traffic.
    The kind is set EXPLICITLY by the harness (``CIRIS_TRACE_RUN_KIND``), never
    inferred from channel names. Only ``MOCK`` blocks remote export; ``QA`` and
    ``BATTERY`` traces may ship but are marked.

    It rides the existing ``deployment_type`` string of the signed
    ``deployment_profile`` / ``correlation_metadata`` blocks: a VALUE change,
    not a wire-shape change, visible to the canonical at every trace level,
    which can refuse ``mock`` at admission (CIRISPersist#1040).
    """

    PRODUCTION = "production"
    QA = "qa"
    BATTERY = "battery"
    MOCK = "mock"


#: Harnesses set this. Values: ``qa`` | ``battery`` | ``production`` (default).
RUN_KIND_ENV_VAR = "CIRIS_TRACE_RUN_KIND"
_run_kind_warned = False


def trace_run_kind() -> TraceRunKind:
    """Resolve the run kind. The mock LLM always wins and cannot be overridden.

    An unrecognized non-empty value fails toward "synthetic" (``QA``) with a
    WARNING: a harness that tried to mark its run must never be read as
    production because of a typo.
    """
    global _run_kind_warned
    if is_mock_llm_active():
        return TraceRunKind.MOCK
    raw = os.environ.get(RUN_KIND_ENV_VAR, "").strip().lower()
    if not raw or raw == TraceRunKind.PRODUCTION.value:
        return TraceRunKind.PRODUCTION
    if raw in (TraceRunKind.QA.value, TraceRunKind.BATTERY.value):
        return TraceRunKind(raw)
    if not _run_kind_warned:
        _run_kind_warned = True
        logger.warning(
            "[RUN-KIND] %s=%r is not one of qa|battery|production (mock comes only from the mock LLM); "
            "marking traces 'qa' so a synthetic run is never read as production.",
            RUN_KIND_ENV_VAR,
            raw,
        )
    return TraceRunKind.QA


def _reset_for_tests() -> None:
    """Clear the latch and the log-once set. Tests only; production never calls it."""
    global _latched_source, _run_kind_warned
    with _lock:
        _latched_source = None
        _refusals_logged.clear()
    _run_kind_warned = False
