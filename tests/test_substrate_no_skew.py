"""Substrate version-skew guard (#896 one-wheel invariant).

The ciris-server wheel re-hosts persist + edge + lens (+ the verify Rust
crate) behind ONE PyO3 type registry. Installing any of the standalone
substrate wheels alongside it recreates the dual-registry cohabitation class:
- ciris-persist / ciris-edge → "'Engine' object is not an instance of
  'Engine'" (two type registries for the same types)
- ciris-lens-core → Requires ciris-persist, which reinstalls a second
  persist and broke the lens seal with verify_unknown_key (2026-06 CI)

This test makes the invariant a hard gate: when ciris-server is installed,
none of the standalone substrate wheels may be co-installed. The Python
ciris-verify wheel is EXEMPT — a leftover install is harmless (it is a
C-ABI client artifact, not a second PyO3 type registry). As of the 2.9.7
DRY purge the agent no longer pins or imports it: tree_verify rides the
ciris-server wheel's ``ciris_verify_tree`` C symbol directly.
"""

from __future__ import annotations

import importlib.metadata as md

import pytest

_FORBIDDEN_ALONGSIDE_SERVER = ["ciris-persist", "ciris-edge", "ciris-lens-core"]


def _installed(dist: str) -> str | None:
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def test_no_standalone_substrate_alongside_one_wheel() -> None:
    server = _installed("ciris-server")
    if server is None:
        pytest.skip("ciris-server not installed (pre-adoption environment)")
    offenders = {d: v for d in _FORBIDDEN_ALONGSIDE_SERVER if (v := _installed(d))}
    assert not offenders, (
        f"version-skew risk: ciris-server {server} is installed but standalone "
        f"substrate wheels are co-installed: {offenders}. The one wheel re-hosts "
        "persist/edge/lens — uninstall the standalone wheels (dual PyO3 type "
        "registries break Engine identity and the lens seal)."
    )


def test_substrate_seam_uses_the_one_wheel() -> None:
    """When ciris-server is installed, the seam must resolve to it."""
    if _installed("ciris-server") is None:
        pytest.skip("ciris-server not installed (pre-adoption environment)")
    from ciris_engine.logic.persistence import _substrate

    assert getattr(_substrate, "SUBSTRATE_SOURCE", None) == "ciris_server", (
        f"substrate seam resolved to {getattr(_substrate, 'SUBSTRATE_SOURCE', None)!r} "
        "despite ciris-server being installed"
    )
