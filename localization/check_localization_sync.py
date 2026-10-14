"""Agent adapter: the bundle the vendored ``localize.py`` works against.

AGENT-OWNED -- not a vendored file (see ``localization/VENDORED.md``).

``localize.py`` (vendored byte-identical from CIRISClient) does
``import check_localization_sync as guard`` and reads five things from it:
``CANONICAL_BUNDLE``, ``MIRROR_BUNDLES``, ``flat_values``,
``manifest_languages`` and ``_PLACEHOLDER``. Upstream, that module is the
client's strict gate at ``client/tools/check_localization_sync.py``, whose
bundle paths are the four KMP client bundles. CIRISAgent has none of those.

This module sits FIRST on ``localize.py``'s import path (it inserts its own
directory), so it is what ``import check_localization_sync`` resolves to here.
It loads the vendored gate unchanged from ``localization/upstream/`` and
re-exports its primitives -- the placeholder grammar and the flattening are the
upstream definitions, not copies -- and replaces only the bundle locations:

``LOCALIZE_TARGET=ui`` (default)
    ``ciris_engine/data/localized/{lang}.json`` -- the agent's own string and
    prompt bundle, single copy. The ``apps/`` bundles are CIRISClient's and are
    not written from here. ``prompts.language_guidance`` is excluded from every
    key set: it is a per-language primer authored for that language, not a
    translation of the English one (localization/CLAUDE.md).

``LOCALIZE_TARGET=accord``
    the Accord segment bundle staged by ``accord_localize.py`` at
    ``LOCALIZE_ACCORD_STAGE``. Not meant to be selected by hand.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Pattern, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
UPSTREAM_GUARD = HERE / "upstream" / "check_localization_sync.py"

UI_BUNDLE = "ciris_engine/data/localized"

#: Subtrees of the UI bundle that are per-language content, not translations.
UI_EXCLUDED_PREFIXES: Tuple[str, ...] = ("prompts.language_guidance",)


def _load_upstream() -> ModuleType:
    name = "ciris_client_check_localization_sync"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, UPSTREAM_GUARD)
    if spec is None or spec.loader is None:
        raise SystemExit(f"[refuse] cannot load the vendored guard at {UPSTREAM_GUARD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


upstream = _load_upstream()

TARGET = os.environ.get("LOCALIZE_TARGET", "ui").strip() or "ui"

if TARGET == "ui":
    CANONICAL_BUNDLE = UI_BUNDLE
    EXCLUDED_PREFIXES: Tuple[str, ...] = UI_EXCLUDED_PREFIXES
elif TARGET == "accord":
    _stage = os.environ.get("LOCALIZE_ACCORD_STAGE", "")
    if not _stage:
        raise SystemExit(
            "[refuse] LOCALIZE_TARGET=accord needs LOCALIZE_ACCORD_STAGE; run "
            "localization/accord_localize.py, which stages the segment bundle"
        )
    # Absolute on purpose: localize.py joins it onto its REPO_ROOT, and joining
    # an absolute path yields the path itself.
    CANONICAL_BUNDLE = str(Path(_stage).resolve())
    EXCLUDED_PREFIXES = ()
else:
    raise SystemExit(f"[refuse] LOCALIZE_TARGET={TARGET!r}: expected 'ui' or 'accord'")

#: One bundle, one copy. ``insert`` writes every entry here.
MIRROR_BUNDLES: Tuple[str, ...] = (CANONICAL_BUNDLE,)

# The upstream definitions, re-exported unchanged.
_PLACEHOLDER: Pattern[str] = upstream._PLACEHOLDER
_IGNORED_ROOTS = upstream._IGNORED_ROOTS
load_json = upstream.load_json
manifest_languages = upstream.manifest_languages
resolve_key = upstream.resolve_key


def _excluded(key: str) -> bool:
    return any(key == p or key.startswith(p + ".") for p in EXCLUDED_PREFIXES)


def flat_values(obj: Dict[str, Any], prefix: str = "", top: bool = True) -> Dict[str, Any]:
    """Upstream ``flat_values``, minus this target's excluded subtrees."""
    flat: Dict[str, Any] = upstream.flat_values(obj, prefix, top)
    if not EXCLUDED_PREFIXES:
        return flat
    return {k: v for k, v in flat.items() if not _excluded(k)}
