"""#1011 — the .fwork redirect and the embed script must name the same framework.

Two files compute the iOS framework name independently:

  * ``tools/update_substrate_libs.py`` writes the ``.fwork`` redirect, whose
    contents point at ``Frameworks/<name>.framework/<name>``.
  * ``apps/ios/scripts/embed_native_frameworks.sh`` builds the framework
    from the ``.so`` sitting under ``app_packages_native/``, deriving the name
    from that path.

Neither side can catch a mismatch alone. Each is individually valid; only the
PAIR is wrong. That is the whole reason this test exists, and the reason it
parses the shell script rather than restating what the shell script does — a
second copy of the same assumption would agree with the first and prove
nothing.

The bug it locks out: ``fw_name = f"{pkg}.{pkg}"`` agreed with the shell script
only because persist, edge and lens name their module after their package.
CIRISServer's module is an in-package submodule (``ciris_server._native``), so
the builder produced ``ciris_server.ciris_server`` while the embed script
produced ``ciris_server._native``, and the redirect pointed at a framework that
is never built.

The failure mode is the one worth a gate: the iOS asset exists, the refresh
workflow's asset check passes, CI goes green, and the dangling redirect
surfaces only at app launch on a device.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
BUILDER = REPO / "tools/update_substrate_libs.py"
EMBED = REPO / "apps/ios/scripts/embed_native_frameworks.sh"

sys.path.insert(0, str(REPO))


def _pyo3_libs():
    from tools.update_substrate_libs import LIBS

    return {k: v for k, v in LIBS.items() if v.is_pyo3}


def _framework_name_per_shell_script(module_path: str) -> str:
    """Apply the transform the SHELL SCRIPT declares, read out of the script.

    Reads the two substitutions rather than hardcoding them, so that editing the
    shell script and not this test is caught here instead of on a device.
    """
    text = EMBED.read_text(encoding="utf-8")

    # The script strips several suffixes IN ORDER:
    #   MODULE_PATH="${MODULE_PATH%.cpython-*}"
    #   MODULE_PATH="${MODULE_PATH%.abi3.so}"
    #   MODULE_PATH="${MODULE_PATH%.so}"
    # All of them, in source order — taking only the first would model a
    # different script than the one that runs.
    strips = re.findall(r'MODULE_PATH="\$\{MODULE_PATH%([^}"]+)\}"', text)
    assert strips, "embed_native_frameworks.sh no longer strips suffixes from MODULE_PATH"

    out = module_path
    for pattern in strips:
        # `${VAR%pattern}` removes the shortest matching suffix; the patterns are
        # shell globs, so `.cpython-*` has to be matched as a glob, not literally.
        if "*" in pattern or "?" in pattern:
            rx = re.compile(re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + r"\Z")
            m = rx.search(out)
            if m:
                out = out[: m.start()]
        elif out.endswith(pattern):
            out = out[: -len(pattern)]

    # FRAMEWORK_NAME=$(echo "$MODULE_PATH" | tr '/' '.') — specifically the `tr`
    # applied to MODULE_PATH. The script also runs `tr '_' '-'` for bundle ids,
    # and matching that one instead silently models the wrong transform.
    tr = re.search(r'FRAMEWORK_NAME=\$\(echo\s+"\$MODULE_PATH"\s*\|\s*tr\s+\'(.)\'\s+\'(.)\'\)', text)
    assert tr, "embed_native_frameworks.sh no longer derives FRAMEWORK_NAME from MODULE_PATH via tr"
    return out.replace(tr.group(1), tr.group(2))


@pytest.mark.parametrize("key", sorted(_pyo3_libs()))
def test_fwork_redirect_matches_what_the_embed_script_builds(key: str) -> None:
    from tools.update_substrate_libs import LIBS

    lib = LIBS[key]
    assert lib.dylib_filename, (
        f"{key}: is_pyo3 with an empty dylib_filename. The framework stem is derived "
        f"from the artifact name, so an empty one yields '{lib.bindings_package}.' — a "
        f"redirect to a framework that cannot exist."
    )

    # What the builder ACTUALLY computes — called, not reimplemented. A local
    # copy of the formula would agree with itself and survive a revert of the fix.
    from tools.update_substrate_libs import pyo3_framework_name

    builder_name = pyo3_framework_name(lib)

    # What the embed script derives from the same on-disk path.
    shell_name = _framework_name_per_shell_script(f"{lib.bindings_package}/{lib.dylib_filename}")

    assert builder_name == shell_name, (
        f"{key}: the .fwork redirect names {builder_name!r} but embed_native_frameworks.sh "
        f"builds {shell_name!r} from app_packages_native/{lib.bindings_package}/"
        f"{lib.dylib_filename}. The redirect would dangle and only fail at app launch."
    )


def test_the_builder_derives_the_stem_from_the_artifact() -> None:
    """The regression guard proper.

    Asserted on the source rather than the output because the output is only
    wrong for a lib whose module name differs from its package name — which was
    exactly zero of the registered libs until CIRISServer. A test that only
    checked outputs would have passed on every lib that existed when the bug
    was written.
    """
    src = BUILDER.read_text(encoding="utf-8")
    assert 'fw_name = f"{lib.bindings_package}.{lib.bindings_package}"' not in src, (
        "bundle_pyo3_module is naming the framework {pkg}.{pkg} again. That holds only "
        "while every module is named after its package; it silently breaks for an "
        "in-package submodule like ciris_server._native."
    )
    assert "fw_stem" in src, "the artifact-derived stem is gone"


def test_ciris_server_is_registered_for_ios() -> None:
    """The specific entry #1011 was filed to add."""
    from tools.update_substrate_libs import LIBS

    server = LIBS["server"]
    assert server.dylib_filename == "_native.abi3.so", (
        "CIRISServer's pymodule exports PyInit__native, so the published slice must be "
        "_native.abi3.so — a ciris_server.abi3.so would need PyInit_ciris_server, which "
        "does not exist."
    )
    assert server.device_dir == "ios-device"
    assert server.simulator_dir == "ios-simulator"
