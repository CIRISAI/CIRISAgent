"""The Android shell's Compose version must follow the plugin, never a hand pin.

The client .aar is a bare archive with no POM, so nothing at build time can say
what Compose it needs. CIRISClient builds it with the `org.jetbrains.compose`
plugin's accessors, so its bytecode tracks whatever Jetpack Compose that plugin
version maps to. We apply the same plugin, but our shell hand-pinned
`androidx.compose.ui:ui:1.6.1` -- capping the graph below the 1.7.0 that
introduced Composer.startReplaceGroup, which the .aar calls. The app died on its
first recomposition with NoSuchMethodError, only on the device, and the gate
could not even see why until the logcat was collected (run 33706020778).

Going through the accessors makes our version follow the plugin exactly as the
client's does, so the two cannot drift apart silently. This pins that shape.
"""

from __future__ import annotations

import re
from pathlib import Path

GRADLE = Path(__file__).resolve().parents[2] / "apps" / "android" / "build.gradle"

# The core Compose artifacts. A hand pin on any of these re-caps the graph.
_CORE = ("runtime:runtime", "ui:ui", "foundation:foundation", "material3:material3", "animation:animation")


def _deps_block() -> str:
    src = GRADLE.read_text(encoding="utf-8")
    # Only the dependencies {} body matters; comments elsewhere may quote old pins.
    m = re.search(r"dependencies\s*\{(.*)\n\}", src, re.S)
    assert m, "no dependencies block in apps/android/build.gradle"
    body = m.group(1)
    # Drop comment lines: the explanation deliberately quotes the old pin.
    return "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))


def test_no_core_compose_artifact_is_hand_pinned() -> None:
    body = _deps_block()
    offenders = [
        line.strip()
        for line in body.splitlines()
        if re.search(r"androidx\.compose\.(" + "|".join(re.escape(c) for c in _CORE) + r"):\d", line)
    ]
    assert not offenders, (
        "core Compose must come from the plugin accessors (compose.runtime, compose.ui, ...), "
        f"not a version literal that can fall below what the client .aar was built against: {offenders}"
    )


def test_core_compose_comes_through_the_plugin_accessors() -> None:
    body = _deps_block()
    for accessor in ("compose.runtime", "compose.ui", "compose.foundation", "compose.material3"):
        assert re.search(rf"implementation\s+{re.escape(accessor)}\b", body), f"missing `implementation {accessor}`"


def test_the_shell_applies_the_same_compose_plugin_the_client_uses() -> None:
    """The accessors are only a fix if the plugin is actually applied here."""
    src = GRADLE.read_text(encoding="utf-8")
    assert re.search(r'id\s+"org\.jetbrains\.compose"', src), "org.jetbrains.compose plugin not applied to :android"
