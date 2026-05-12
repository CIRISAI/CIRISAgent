"""Module-metadata reader for the QA runner.

Modules declare their CI requirements as **class attributes** so the
runner can configure live-mode, env vars, etc. without per-module
hardcoding in the runner itself.

Recognized class attributes on test modules:

  REQUIRES_LIVE_LLM : bool          — runner forces ``--live`` (with
                                      defaults from LIVE_LLM_DEFAULTS).
                                      Refuses to start in mock-LLM mode.
  LIVE_LLM_DEFAULTS : dict[str,str] — used when ``--live`` is not
                                      explicitly configured. Keys:
                                      key_file / base_url / model /
                                      provider.
  SERVER_ENV : dict[str, str]       — merged into the agent process env
                                      at server-start time. Use for
                                      module-specific knobs like
                                      CIRIS_DISABLE_TASK_APPEND=1 or
                                      CIRIS_API_INTERACTION_TIMEOUT.
  WIPE_DATA_ON_START : bool         — runner forces --wipe-data
                                      regardless of CLI flags. Required
                                      for signed-artifact reproducibility
                                      (see CIRISNodeCore FSD/SAFETY_BATTERY_CI_LOOP.md
                                      §5.1).
  REQUIRES_CIRIS_SERVER : bool      — defaults True. Set False for modules
                                      that don't talk to a CIRIS API server
                                      at all (e.g. safety_interpret, which
                                      calls the Anthropic API directly with
                                      no agent in the loop). When all
                                      selected modules declare this False,
                                      the runner skips server start + auth.

The runner reads these via :func:`get_metadata` which lazy-imports the
module to avoid CLI startup cost.

Adding a new module with CI requirements:
  1. Set the class attributes on the test module class.
  2. Add a ``(QAModule, "import_path", "ClassName")`` entry to
     ``_REGISTRY`` below.
  3. The runner picks the rest up automatically.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Dict

from ..config import QAModule


# (QAModule → import path → class name). Lazy-imported when get_metadata
# is called; avoids dragging every test module into CLI parse time.
_REGISTRY: Dict[QAModule, tuple] = {
    QAModule.SAFETY_BATTERY: ("tools.qa_runner.modules.safety_battery", "SafetyBatteryTests"),
    QAModule.SAFETY_INTERPRET: ("tools.qa_runner.modules.safety_interpret", "SafetyInterpretTests"),
    QAModule.MODEL_EVAL: ("tools.qa_runner.modules.model_eval_tests", "ModelEvalTests"),
    QAModule.PARALLEL_LOCALES: ("tools.qa_runner.modules.parallel_locales_tests", "ParallelLocalesTests"),
    QAModule.DEGRADED_MODE: ("tools.qa_runner.modules.degraded_mode_tests", "DegradedModeTests"),
}


@dataclass
class ModuleMetadata:
    """Resolved metadata for a QA module."""

    requires_live_llm: bool = False
    live_llm_defaults: Dict[str, str] = field(default_factory=dict)
    server_env: Dict[str, str] = field(default_factory=dict)
    wipe_data_on_start: bool = False
    requires_ciris_server: bool = True


def get_metadata(module: QAModule) -> ModuleMetadata:
    """Read module-class metadata. Returns defaults if the module class
    cannot be imported or declares no metadata."""
    entry = _REGISTRY.get(module)
    if not entry:
        return ModuleMetadata()
    import_path, class_name = entry
    try:
        mod = importlib.import_module(import_path)
        cls: Any = getattr(mod, class_name, None)
    except Exception:
        return ModuleMetadata()
    if cls is None:
        return ModuleMetadata()
    return ModuleMetadata(
        requires_live_llm=bool(getattr(cls, "REQUIRES_LIVE_LLM", False)),
        live_llm_defaults=dict(getattr(cls, "LIVE_LLM_DEFAULTS", {})),
        server_env=dict(getattr(cls, "SERVER_ENV", {})),
        wipe_data_on_start=bool(getattr(cls, "WIPE_DATA_ON_START", False)),
        requires_ciris_server=bool(getattr(cls, "REQUIRES_CIRIS_SERVER", True)),
    )


def merge_server_env(modules: list) -> Dict[str, str]:
    """Merge the SERVER_ENV declarations from every selected module.

    Conflicts (same key with different values across modules) are
    resolved last-write-wins, with a flag in the metadata for the
    runner to log. Most CI runs select one module at a time, so
    conflicts are rare.
    """
    merged: Dict[str, str] = {}
    conflicts: Dict[str, list] = {}
    for m in modules:
        md = get_metadata(m)
        for k, v in md.server_env.items():
            if k in merged and merged[k] != v:
                conflicts.setdefault(k, [merged[k]]).append(v)
            merged[k] = v
    # Stash conflicts on the dict for caller introspection; not strictly
    # part of the API, but lets the runner log a warning without losing
    # the actual merged values.
    merged.setdefault("__conflicts__", "")
    if conflicts:
        merged["__conflicts__"] = ";".join(
            f"{k}={','.join(map(str, vs))}" for k, vs in conflicts.items()
        )
    return merged
