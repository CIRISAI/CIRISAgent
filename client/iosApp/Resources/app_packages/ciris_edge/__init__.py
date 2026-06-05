"""UniFFI bindings bridge — v0.13.0 (CIRISEdge#36 GO).

The wheel ships `libciris_edge.so` (Linux) / `libciris_edge.dylib` (Darwin)
as `ciris_edge.abi3.so` (PyO3 maturin abi3 rename). UniFFI's generated
loader `_uniffi_load_indirect()` in `bindings/python/ciris_edge.py`
hard-codes `lib{}.so` / `lib{}.dylib` lookup paths — which won't find
the abi3-renamed file in the wheel layout.

This wrapper sidesteps that by:

  1. Locating the already-loaded `ciris_edge` extension module (PyO3
     side) — that's the same `.so` UniFFI needs.
  2. Patching the UniFFI loader to return the existing `ctypes.CDLL`
     handle instead of dlopen-ing a second copy.
  3. `exec()`-ing the generated `ciris_edge.py` against this module's
     namespace so the bound symbols (`peer_list`, `transport_list`,
     `identity_hash`, `metrics_snapshot`, ...) appear under
     `ciris_edge.uniffi_bindings.X`.

Per the spike's NO-GO carve-out:

  - `from ciris_edge import PyEdge`                — PyO3 surface
    (init_edge_runtime, Tier 2 GIL-drainer callbacks, AsyncIterator)
  - `from ciris_edge.uniffi_bindings import peer_list, transport_list, ...`
    — UniFFI surface (#25 / #26 / #31 reads / #28 snapshot reads)

Both bind to the same `.so`; `nm -D` will show both
`PyInit_ciris_edge` AND `uniffi_ciris_edge_fn_func_*` symbols.

# Init order

The PyO3 `init_edge_runtime(engine, ...)` constructs the `PyEdge` AND
populates the UniFFI-side process-global `Weak<Edge>` slot
(via `crate::ffi::uniffi_impl::install_edge_handle`). Calls to the
UniFFI functions BEFORE `init_edge_runtime` raise `EdgeBindingsError.NotInitialized`.

# Lifetime

The UniFFI free functions hold a `Weak<Edge>` — they do NOT keep
the Edge alive. When the Python `PyEdge` handle is gc'd and the
underlying `Arc<Edge>` is dropped, subsequent UniFFI calls return
`NotInitialized`. Consumers SHOULD retain the `PyEdge` reference
for the lifetime of their UniFFI usage.
"""

from __future__ import annotations

import ctypes
import pathlib
import sys
import types


def _resolve_cdylib() -> ctypes.CDLL:
    """Locate the loaded `ciris_edge` extension `.so` and return a
    `ctypes.CDLL` handle.

    The PyO3-exported extension lives at `ciris_edge.ciris_edge`
    (the inner module created by `#[pymodule] fn ciris_edge(...)`
    inside `src/ffi/pyo3.rs`); the wheel layout is:

        site-packages/ciris_edge/__init__.py        ← Python package
        site-packages/ciris_edge/ciris_edge.abi3.so ← PyO3 cdylib

    Both names ARE necessary — `ciris_edge` the package wraps
    `ciris_edge.ciris_edge` the extension. Importing the inner
    module triggers `PyInit_ciris_edge`; we then resolve its file
    path and dlopen the same `.so` via ctypes (reusing the resident
    copy, no double-init).
    """
    try:
        # Trigger Python's normal extension load path. Side-effect:
        # `PyInit_ciris_edge` runs once, registering the PyO3
        # classes/functions on the inner module.
        from ciris_edge import ciris_edge as _inner_mod  # noqa: F401
    except ImportError as exc:  # pragma: no cover — wheel install gates
        raise RuntimeError(
            "uniffi_bindings: parent `ciris_edge.ciris_edge` extension not "
            f"importable ({exc!r}). The UniFFI surface requires the PyO3 entry "
            "point to be loaded first; check that the wheel is installed correctly."
        ) from exc

    inner = sys.modules.get("ciris_edge.ciris_edge")
    if inner is None or not getattr(inner, "__file__", None):
        raise RuntimeError(
            "uniffi_bindings: `ciris_edge.ciris_edge` is loaded but has no "
            "__file__ attribute — cannot locate the underlying shared library. "
            "This usually means a frozen / pyinstaller-bundled deployment "
            "that the v0.13.0 wrapper doesn't yet support."
        )
    cdylib_path = pathlib.Path(inner.__file__).resolve()
    if not cdylib_path.exists():
        raise RuntimeError(f"uniffi_bindings: extension path missing: {cdylib_path}")
    # `RTLD_GLOBAL` mirrors how Python's own importer dlopens
    # extension modules — reuses the resident copy, doesn't double-init.
    flags = ctypes.RTLD_GLOBAL
    return ctypes.CDLL(str(cdylib_path), mode=flags)


def _load_uniffi_bindings_module(cdylib: ctypes.CDLL) -> types.ModuleType:
    """Load `bindings/python/ciris_edge.py` and patch its CDLL
    loader to return our handle. Returns the loaded module.

    The generated file is shipped INSIDE the wheel via
    `[tool.maturin] include` — at install-time it lives at
    `<site-packages>/ciris_edge/uniffi_bindings/_generated.py`.
    """
    # The committed generator output is bundled into the wheel via
    # `[tool.maturin] include = ["bindings/python/ciris_edge.py"]`
    # — at install-time the file lands at
    # `<site-packages>/bindings/python/ciris_edge.py`. For dev builds
    # the same file lives at `<repo>/bindings/python/ciris_edge.py`
    # relative to this wrapper at `<repo>/python/ciris_edge/uniffi_bindings/`.
    here = pathlib.Path(__file__).resolve().parent
    # Path layouts:
    #
    #   installed wheel: <site-packages>/ciris_edge/uniffi_bindings/__init__.py
    #                  + <site-packages>/bindings/python/ciris_edge.py
    #     here.parent.parent == <site-packages>
    #
    #   dev source tree: <repo>/python/ciris_edge/uniffi_bindings/__init__.py
    #                  + <repo>/bindings/python/ciris_edge.py
    #     here.parent.parent.parent == <repo>
    candidates = [
        here.parent.parent / "bindings" / "python" / "ciris_edge.py",
        here.parent.parent.parent / "bindings" / "python" / "ciris_edge.py",
        # Sibling fallback: a future "embedded" layout copies the
        # generated file next to this wrapper as `_generated.py`.
        here / "_generated.py",
    ]
    src_path = next((p for p in candidates if p.exists()), None)
    if src_path is None:
        raise RuntimeError(
            "uniffi_bindings: generated `ciris_edge.py` not found in any of: "
            + ", ".join(str(c) for c in candidates)
        )

    # The generated file does
    #   _UniffiLib = _uniffi_load_indirect()
    # at module-load time, where `_uniffi_load_indirect()` calls
    # `ctypes.cdll.LoadLibrary(path)` with an OS-formatted path that
    # doesn't account for maturin's abi3 rename. We string-patch the
    # source so the function body returns our already-resolved CDLL
    # before the module-load-time call binds `_UniffiLib`.
    source = src_path.read_text()
    sentinel_def = "def _uniffi_load_indirect():"
    if sentinel_def not in source:
        raise RuntimeError(
            f"uniffi_bindings: cannot find `{sentinel_def}` in {src_path} — "
            "generated file shape changed; the wrapper needs updating."
        )

    # Replace the entire function body with `return _UNIFFI_PRELOADED_CDLL`.
    # The preloaded handle is injected into the module's namespace
    # before exec — it's a fresh global the patched body resolves.
    patched_source = source.replace(
        sentinel_def,
        sentinel_def + "\n    return _UNIFFI_PRELOADED_CDLL  # patched by uniffi_bindings\n    # original body follows but is dead code:",
        1,
    )

    module_name = "ciris_edge._uniffi_generated"
    module = types.ModuleType(module_name)
    module.__file__ = str(src_path)
    module.__dict__["_UNIFFI_PRELOADED_CDLL"] = cdylib
    sys.modules[module_name] = module
    exec(compile(patched_source, str(src_path), "exec"), module.__dict__)  # noqa: S102
    return module


# Bootstrap — runs at first `import ciris_edge.uniffi_bindings`.
_cdylib = _resolve_cdylib()
_uniffi_module = _load_uniffi_bindings_module(_cdylib)


# Re-export every public symbol the generated module exposes. The UDL
# declares each function + type at the namespace level; the generated
# file emits them as bare globals. We mirror them into THIS module's
# namespace so `from ciris_edge.uniffi_bindings import peer_list`
# works.
def _is_public(name: str) -> bool:
    return not name.startswith("_") and name not in {
        "annotations",
        "ctypes",
        "datetime",
        "enum",
        "itertools",
        "os",
        "struct",
        "sys",
        "typing",
        "platform",
        "threading",
        "contextlib",
        "traceback",
    }


for _name in dir(_uniffi_module):
    if _is_public(_name):
        globals()[_name] = getattr(_uniffi_module, _name)
del _name


def _exports() -> list[str]:
    return sorted(n for n in globals() if _is_public(n))


__all__ = _exports()
