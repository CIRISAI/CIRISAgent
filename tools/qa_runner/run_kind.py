"""The run-kind declaration every QA-runner launch carries (CIRISAgent#1245).

Every agent a harness in this package starts is a harness run, including a
live-model run. Ruling (2026-10-14): QA runs are valuable but must be
identified as such, and anything outside a harness is production. So a harness
never forwards ``production``: an inherited ``production`` (or an unrecognized
value) is replaced with the harness's own kind, and only an explicit ``qa`` or
``battery`` is kept.

The agent-side resolver (``ciris_engine.logic.utils.mock_llm_guard``) reads the
same variable; the mock LLM still overrides both with ``mock`` there.
"""

from __future__ import annotations

import os
from typing import FrozenSet, Iterable, List, MutableMapping, Optional

#: Mirrors ``mock_llm_guard.RUN_KIND_ENV_VAR``; a test pins the two together.
RUN_KIND_ENV_VAR = "CIRIS_TRACE_RUN_KIND"

QA = "qa"
BATTERY = "battery"
_HARNESS_KINDS = (QA, BATTERY)


def _battery_modules() -> FrozenSet[object]:
    from .config import QAModule  # local import: config imports half the package

    # Real-model evaluation runs whose traces are research rows, not QA rows.
    return frozenset({QAModule.SAFETY_BATTERY, QAModule.MODEL_EVAL, QAModule.HE300_BENCHMARK})


def harness_run_kind(modules: Optional[Iterable[object]] = None) -> str:
    """``battery`` when any selected module is an evaluation battery, else ``qa``."""
    battery = _battery_modules()
    return BATTERY if any(m in battery for m in (modules or [])) else QA


def resolve_run_kind(inherited: Optional[str], default: str = QA) -> str:
    """Keep an explicit ``qa`` / ``battery``; anything else becomes ``default``."""
    value = (inherited or "").strip().lower()
    return value if value in _HARNESS_KINDS else default


def declare_run_kind(env: MutableMapping[str, str], default: str = QA) -> Optional[str]:
    """Write the run kind into ``env``. Returns a warning when an inherited value was replaced.

    Never leaves ``production`` (or a typo) in a harness env: an inherited
    ``production`` would otherwise ship a harness run's traces as production.
    """
    inherited = (env.get(RUN_KIND_ENV_VAR) or "").strip()
    resolved = resolve_run_kind(inherited, default)
    env[RUN_KIND_ENV_VAR] = resolved
    if inherited and inherited.lower() != resolved:
        return (
            f"{RUN_KIND_ENV_VAR}={inherited!r} was inherited; a harness run is never production, "
            f"so it is set to {resolved!r}"
        )
    return None


def declare_process_run_kind(default: str = QA) -> Optional[str]:
    """``declare_run_kind`` on this process's own ``os.environ``.

    Called at each harness entry point so every launcher it reaches (web_ui,
    mobile, he300, sibling module launches) inherits the declaration.
    """
    return declare_run_kind(os.environ, default)


def forwarded_run_kind() -> str:
    """The kind to forward into a device or app process this harness launches."""
    return resolve_run_kind(os.environ.get(RUN_KIND_ENV_VAR), QA)


def ios_simctl_env(env: MutableMapping[str, str]) -> None:
    """``simctl launch`` forwards only ``SIMCTL_CHILD_``-prefixed vars into the app."""
    env[f"SIMCTL_CHILD_{RUN_KIND_ENV_VAR}"] = forwarded_run_kind()


#: Android system property the agent reads (``mock_llm_guard.ANDROID_RUN_KIND_PROP``).
ANDROID_RUN_KIND_PROP = "debug.ciris.trace_run_kind"


def android_setprop_args() -> List[str]:
    """``adb`` args that write the run kind where the Android backend reads it."""
    return ["shell", "setprop", ANDROID_RUN_KIND_PROP, forwarded_run_kind()]
