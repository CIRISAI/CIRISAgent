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
from typing import Iterable, Optional, Set
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


#: Module names that are the mock LLM (``main.py`` uses ``mock_llm``; the
#: manifest's own name is ``mockllm``; modular entries carry a ``modular:`` prefix).
_MOCK_LLM_MODULE_NAMES = frozenset({"mock_llm", "mockllm"})


def latch_if_mock_llm_module(modules: Iterable[object], source: str) -> bool:
    """Latch when a configured module list names the mock LLM. Returns whether it did.

    Called with the runtime's bootstrap modules BEFORE the edge initializes, so a
    mock supplied only through ``RuntimeBootstrapConfig.modules`` (embedded and
    mobile hosts) is known before any federation path starts.
    """
    for module in modules:
        name = str(module).strip().lower()
        if name.startswith("modular:"):
            name = name[len("modular:") :]
        if name.rsplit(".", 1)[-1] in _MOCK_LLM_MODULE_NAMES:
            mark_mock_llm_active(f"{source}:{module}")
            return True
    return False


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
    ``BATTERY`` traces may ship but are marked. ``PROD_PERSONAL`` and
    ``PROD_MANAGED`` label a production run's deployment; ``PRODUCTION`` stays
    valid (see :func:`wire_run_kind`).

    Under trace_format v2.7.0 a non-production kind rides the existing
    ``deployment_type`` string of the signed ``deployment_profile`` /
    ``correlation_metadata`` blocks (CIRISPersist#1040). Under v2.8.0 it is the
    signed member ``deployment_profile.run_kind`` (CIRISAgent#1249, CC 3.1.5).
    """

    PRODUCTION = "production"
    #: A production run on a personal install (trace_format v2.8.0 only).
    PROD_PERSONAL = "prod-personal"
    #: A production run on a CIRISManager-managed deployment (v2.8.0 only).
    PROD_MANAGED = "prod-managed"
    QA = "qa"
    BATTERY = "battery"
    MOCK = "mock"

    @property
    def is_production(self) -> bool:
        """``production``, ``prod-personal`` and ``prod-managed`` are all production runs.

        Admission treats the three alike; only the label differs. Under
        trace_format v2.7.0 every production kind leaves ``deployment_type``
        untouched, so those bytes do not change.
        """
        return self in _PRODUCTION_KINDS


_PRODUCTION_KINDS = frozenset({TraceRunKind.PRODUCTION, TraceRunKind.PROD_PERSONAL, TraceRunKind.PROD_MANAGED})
_PRODUCTION_VALUES = frozenset(k.value for k in _PRODUCTION_KINDS)

#: Harnesses set this. Values: ``qa`` | ``battery`` | ``production`` (default).
#: An operator may also declare ``prod-personal`` or ``prod-managed`` here.
RUN_KIND_ENV_VAR = "CIRIS_TRACE_RUN_KIND"
#: CIRISManager sets ``CIRIS_MANAGED=true`` on every agent it deploys
#: (``compose_generator.py``). It is the ONLY managed signal the run kind reads:
#: ``path_resolution.is_managed()`` also counts Docker mounts, so it calls a
#: personal ``install.sh`` Docker install managed.
MANAGED_ENV_VAR = "CIRIS_MANAGED"
_run_kind_warned = False
_override_warned = False


#: Android system property the mobile harness sets with ``adb shell setprop``.
#: An Android app process does not inherit the runner's environment, and an
#: ``am start`` extra reaches the Kotlin activity, not the embedded Python, so
#: this is the one channel the QA harness can write and the runtime can read.
#: ``debug.*`` properties are writable by the adb shell user only.
ANDROID_RUN_KIND_PROP = "debug.ciris.trace_run_kind"
_android_prop_cache: Optional[str] = None


def _android_run_kind_prop() -> str:
    """Read ANDROID_RUN_KIND_PROP once per process; empty off Android or on any error."""
    global _android_prop_cache
    if _android_prop_cache is not None:
        return _android_prop_cache
    value = ""
    if os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA"):
        try:
            import subprocess

            out = subprocess.run(["getprop", ANDROID_RUN_KIND_PROP], capture_output=True, text=True, timeout=5)
            value = (out.stdout or "").strip()
        except Exception:  # noqa: BLE001 - absence of the prop is the normal case
            value = ""
    _android_prop_cache = value
    return value


def _declared_run_kind() -> str:
    """The harness's declaration: process env, then the ``.env`` file, then the Android prop.

    iOS harnesses forward it as ``SIMCTL_CHILD_CIRIS_TRACE_RUN_KIND`` (simctl
    strips the prefix into the app process, which the embedded Python inherits).
    """
    raw = os.environ.get(RUN_KIND_ENV_VAR, "")
    if raw.strip():
        return raw
    try:
        from ciris_engine.logic.config.env_utils import get_env_var

        raw = str(get_env_var(RUN_KIND_ENV_VAR, "") or "")
        if raw.strip():
            return raw
    except Exception:  # noqa: BLE001 - config layer may not be importable this early
        pass
    return _android_run_kind_prop()


def trace_run_kind() -> TraceRunKind:
    """Resolve the run kind. The mock LLM always wins and cannot be overridden.

    An unrecognized non-empty value fails toward "synthetic" (``QA``) with a
    WARNING: a harness that tried to mark its run must never be read as
    production because of a typo.
    """
    global _run_kind_warned
    if is_mock_llm_active():
        return TraceRunKind.MOCK
    raw = _declared_run_kind().strip().lower()
    if not raw:
        return TraceRunKind.PRODUCTION
    if raw in _PRODUCTION_VALUES:
        return TraceRunKind(raw)
    if raw in (TraceRunKind.QA.value, TraceRunKind.BATTERY.value):
        return TraceRunKind(raw)
    if not _run_kind_warned:
        _run_kind_warned = True
        logger.warning(
            "[RUN-KIND] %s=%r is not one of qa|battery|production|prod-personal|prod-managed "
            "(mock comes only from the mock LLM); marking traces 'qa' so a synthetic run is never "
            "read as production.",
            RUN_KIND_ENV_VAR,
            raw,
        )
    return TraceRunKind.QA


def _managed_deployment() -> bool:
    """True when CIRISManager deployed this agent (``CIRIS_MANAGED`` truthy)."""
    return os.environ.get(MANAGED_ENV_VAR, "").strip().lower() in TRUTHY


def wire_run_kind(operator_override: Optional[str] = None) -> TraceRunKind:
    """The run kind trace_format v2.8.0 signs into ``deployment_profile.run_kind``.

    Precedence, highest first:

    1. the mock LLM (``mock``, cannot be overridden);
    2. a harness declaration (``qa`` / ``battery`` via ``CIRIS_TRACE_RUN_KIND``);
    3. the operator override (adapter config ``run_kind``): any value except
       ``mock``; an unknown value fails toward ``qa`` with a WARNING;
    4. an explicit production declaration in ``CIRIS_TRACE_RUN_KIND``
       (``production``, ``prod-personal`` or ``prod-managed``) is kept as is;
    5. undeclared: ``prod-managed`` when ``CIRIS_MANAGED`` is truthy,
       otherwise ``prod-personal``.

    A harness can never be relabelled production by config: steps 1-2 run first.
    """
    global _override_warned
    kind = trace_run_kind()
    if not kind.is_production:
        return kind
    override = (operator_override or "").strip().lower()
    if override:
        if override in _PRODUCTION_VALUES or override in (TraceRunKind.QA.value, TraceRunKind.BATTERY.value):
            return TraceRunKind(override)
        if not _override_warned:
            _override_warned = True
            logger.warning(
                "[RUN-KIND] config run_kind=%r is not one of production|prod-personal|prod-managed|qa|battery; "
                "marking traces 'qa' so a mislabelled run is never read as production.",
                override,
            )
        return TraceRunKind.QA
    if _declared_run_kind().strip():
        return kind
    return TraceRunKind.PROD_MANAGED if _managed_deployment() else TraceRunKind.PROD_PERSONAL


def _reset_for_tests() -> None:
    """Clear the latch and the log-once set. Tests only; production never calls it."""
    global _latched_source, _run_kind_warned, _android_prop_cache, _override_warned
    with _lock:
        _latched_source = None
        _refusals_logged.clear()
    _run_kind_warned = False
    _override_warned = False
    _android_prop_cache = None
