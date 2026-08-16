"""Python wheel surface for the v4.5.0 ``ReconsiderDosGuard``
F-AV-RECONSIDER-DOS defense primitives (CIRISVerify#46 / #50,
v4.7.0 wheel-surface work).

Unlike the v4.2.0 conformance fns on ``CIRISVerify`` (stateless,
input-JSON → output-JSON), the reconsider DoS guard is **stateful**:
it holds per-event rate-limit counters, per-actor rolling-window
budget timestamps, and per-(requester, target) harassment cluster
scores in process memory. So the wheel surface is **handle-based**:
each :class:`ReconsiderDosGuard` instance owns an opaque pointer
into Rust-side memory which is freed in ``__del__``.

Usage::

    from ciris_verify import CIRISVerify

    v = CIRISVerify()
    if v._has_reconsider_dos_support:
        g = v.new_reconsider_dos_guard()
        decision = g.admit_filing(
            event_id="evt-A",
            requester_id="alice",
            target_id="bob",
            now_ms=1_700_000_000_000,
        )
        if decision["admitted"]:
            # ... adjudicate the filing ...
            g.record_outcome("evt-A", "alice", "successful")

Lifecycle / safety story:

- ``ReconsiderDosGuard.__init__`` calls
  ``ciris_verify_reconsider_guard_new``; the FFI returns a leaked
  ``Box<ReconsiderDosGuard>``. The Python instance stores that
  pointer in ``self._handle`` and a reference to the parent
  ``CIRISVerify`` (to keep ``self._lib`` alive — if the CDLL were
  to be GC'd before the guard, ``__del__`` would crash trying to
  call ``ciris_verify_reconsider_guard_free`` through a dangling
  function pointer).
- ``__del__`` calls ``ciris_verify_reconsider_guard_free`` and
  nulls ``self._handle`` so a second ``__del__`` (e.g., during
  interpreter shutdown) is a no-op.
- The Rust guard is **not** ``Sync``. Concurrent ``admit_filing`` /
  ``record_outcome`` calls on the same guard from multiple Python
  threads is undefined behavior at the FFI layer. If you need
  thread-safe access, wrap the guard with a ``threading.Lock`` at
  the call site — the wheel surface deliberately does not impose
  one (the P11 dispatcher in CIRISNodeCore owns the locking
  policy).
"""

from __future__ import annotations

import ctypes
import json
import weakref
from typing import Optional


# ---------------------------------------------------------------------------
# Outcome codes — mirror the i32 contract in
# `src/ciris-verify-ffi/src/wheel_reconsider_dos.rs`.
# ---------------------------------------------------------------------------

_OUTCOME_REJECTED = 0
_OUTCOME_SUCCESSFUL = 1

_OUTCOME_MAP = {
    "rejected": _OUTCOME_REJECTED,
    "successful": _OUTCOME_SUCCESSFUL,
}


# ---------------------------------------------------------------------------
# FFI symbol wiring
# ---------------------------------------------------------------------------


def _wire_reconsider_dos_ffi(verify_instance) -> bool:
    """Wire ctypes argtypes/restype on the FFI symbols this surface needs.

    Returns ``True`` if all four symbols are present in the loaded
    libciris_verify_ffi, ``False`` otherwise (i.e., the loaded wheel
    predates v4.7.0). Idempotent — safe to call repeatedly.
    """
    lib = verify_instance._lib
    if lib is None:
        return False

    try:
        # Handle constructor / destructor.
        lib.ciris_verify_reconsider_guard_new.argtypes = []
        lib.ciris_verify_reconsider_guard_new.restype = ctypes.c_void_p

        lib.ciris_verify_reconsider_guard_free.argtypes = [ctypes.c_void_p]
        lib.ciris_verify_reconsider_guard_free.restype = None

        # admit_filing.
        lib.ciris_verify_reconsider_admit_filing.argtypes = [
            ctypes.c_void_p,                                  # handle
            ctypes.c_char_p,                                  # event_id
            ctypes.c_size_t,                                  # event_id_len
            ctypes.c_char_p,                                  # requester_id
            ctypes.c_size_t,                                  # requester_id_len
            ctypes.c_char_p,                                  # target_id
            ctypes.c_size_t,                                  # target_id_len
            ctypes.c_uint64,                                  # now_ms
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        lib.ciris_verify_reconsider_admit_filing.restype = ctypes.c_int

        # record_outcome.
        lib.ciris_verify_reconsider_record_outcome.argtypes = [
            ctypes.c_void_p,                                  # handle
            ctypes.c_char_p,                                  # event_id
            ctypes.c_size_t,                                  # event_id_len
            ctypes.c_char_p,                                  # requester_id
            ctypes.c_size_t,                                  # requester_id_len
            ctypes.c_int,                                     # outcome
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        lib.ciris_verify_reconsider_record_outcome.restype = ctypes.c_int
        return True
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# Handle wrapper
# ---------------------------------------------------------------------------


class ReconsiderDosGuard:
    """Python wrapper around the Rust ``ReconsiderDosGuard``.

    Each instance owns a leaked ``Box<ReconsiderDosGuard>`` allocated
    by ``ciris_verify_reconsider_guard_new``. The box is reclaimed via
    ``ciris_verify_reconsider_guard_free`` in ``__del__``.

    Do NOT share an instance across threads without your own
    ``threading.Lock`` — the Rust guard is ``!Sync`` and the FFI does
    not lock internally.
    """

    def __init__(self, verify_instance):
        """Allocate a fresh Rust-side guard.

        Args:
            verify_instance: The ``CIRISVerify`` instance whose loaded
                CDLL exposes the reconsider_dos FFI symbols. A weak
                reference is held so the parent's CDLL stays alive at
                least until this guard's ``__del__`` runs.

        Raises:
            RuntimeError: If the loaded CDLL does not expose the
                reconsider_dos symbols, or if the Rust allocator
                returned a null pointer.
        """
        if not getattr(verify_instance, "_has_reconsider_dos_support", False):
            raise RuntimeError(
                "Loaded libciris_verify_ffi does not expose "
                "ciris_verify_reconsider_guard_new — wheel predates v4.7.0."
            )

        # Strong ref to the lib (NOT a weakref to the instance — if the
        # CIRISVerify instance is GC'd while we still hold a Rust
        # allocation, __del__ must still be able to call free()).
        # We keep a hard ref to the CDLL itself; we ALSO keep a weakref
        # to the instance so test code can introspect ownership.
        self._lib = verify_instance._lib
        self._verify_ref = weakref.ref(verify_instance)

        handle = self._lib.ciris_verify_reconsider_guard_new()
        if not handle:
            raise RuntimeError(
                "ciris_verify_reconsider_guard_new returned NULL "
                "(allocation failure or panic in Rust)."
            )
        # ctypes.c_void_p returns an int (or None for NULL); coerce to
        # int so __del__ can safely re-wrap it as c_void_p.
        self._handle: Optional[int] = int(handle)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Explicitly release the Rust-side guard.

        Safe to call multiple times — subsequent calls are no-ops.
        After ``close()``, all other methods on this instance raise
        ``RuntimeError``.
        """
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        # Lib may have been torn down during interpreter shutdown; the
        # try/except keeps __del__ noisy-but-safe instead of crashing.
        try:
            self._lib.ciris_verify_reconsider_guard_free(ctypes.c_void_p(handle))
        except Exception:
            pass

    def __del__(self) -> None:
        # Belt-and-suspenders. close() is idempotent and swallows
        # exceptions to keep interpreter shutdown clean.
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "ReconsiderDosGuard":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # admit_filing
    # ------------------------------------------------------------------

    def admit_filing(
        self,
        event_id: str,
        requester_id: str,
        target_id: str,
        now_ms: int,
    ) -> dict:
        """Run the composed admit-time check.

        Args:
            event_id: The moderation event being reconsidered.
            requester_id: The actor filing the reconsideration.
            target_id: The actor moderated by the underlying event.
            now_ms: Caller-injected wall-clock in milliseconds. The
                Rust module never reads the wall clock — pass in
                ``int(time.time() * 1000)`` at the call site.

        Returns:
            ``{"admitted": True}`` on admission, or
            ``{"admitted": False, "rejection": {...}}`` carrying one
            of the three serde-tagged ``ReconsiderRejection`` variants
            (``EventRateLimited``, ``ActorBudgetExhausted``,
            ``HarassmentClusterDetected``) on rejection.

        Raises:
            RuntimeError: If the guard has been ``close()``d, or if
                the FFI call returns a non-zero status code (null
                pointer, non-UTF-8 input, OOM, panic).
        """
        self._require_open()

        event_bytes = event_id.encode("utf-8")
        requester_bytes = requester_id.encode("utf-8")
        target_bytes = target_id.encode("utf-8")

        result_ptr = ctypes.POINTER(ctypes.c_uint8)()
        result_len = ctypes.c_size_t()

        rc = self._lib.ciris_verify_reconsider_admit_filing(
            ctypes.c_void_p(self._handle),
            event_bytes,
            len(event_bytes),
            requester_bytes,
            len(requester_bytes),
            target_bytes,
            len(target_bytes),
            ctypes.c_uint64(now_ms),
            ctypes.byref(result_ptr),
            ctypes.byref(result_len),
        )
        if rc != 0:
            raise RuntimeError(
                f"ciris_verify_reconsider_admit_filing failed with status {rc}"
            )
        try:
            data = ctypes.string_at(result_ptr, result_len.value)
            return json.loads(data)
        finally:
            # The Rust side allocated this via libc::malloc; reclaim
            # via the same ciris_verify_free symbol the rest of the
            # client uses.
            self._lib.ciris_verify_free(result_ptr)

    # ------------------------------------------------------------------
    # record_outcome
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        event_id: str,
        requester_id: str,
        outcome: str,
    ) -> None:
        """Record the outcome of a previously-admitted filing.

        - ``"successful"`` → releases the per-event rate-limit slot
          AND refills one budget slot for ``requester_id``.
        - ``"rejected"`` → releases the per-event rate-limit slot
          but does NOT refill the budget.

        Args:
            event_id: Same identifier passed to ``admit_filing``.
            requester_id: Same identifier passed to ``admit_filing``.
            outcome: Either ``"successful"`` or ``"rejected"``.

        Raises:
            ValueError: If ``outcome`` is not one of the two known
                strings.
            RuntimeError: If the guard has been ``close()``d, or if
                the FFI call returns a non-zero status code.
        """
        self._require_open()

        if outcome not in _OUTCOME_MAP:
            raise ValueError(
                f"outcome must be 'successful' or 'rejected', got {outcome!r}"
            )
        outcome_code = _OUTCOME_MAP[outcome]

        event_bytes = event_id.encode("utf-8")
        requester_bytes = requester_id.encode("utf-8")

        result_ptr = ctypes.POINTER(ctypes.c_uint8)()
        result_len = ctypes.c_size_t()

        rc = self._lib.ciris_verify_reconsider_record_outcome(
            ctypes.c_void_p(self._handle),
            event_bytes,
            len(event_bytes),
            requester_bytes,
            len(requester_bytes),
            ctypes.c_int(outcome_code),
            ctypes.byref(result_ptr),
            ctypes.byref(result_len),
        )
        if rc != 0:
            raise RuntimeError(
                f"ciris_verify_reconsider_record_outcome failed with status {rc}"
            )
        # Drain the (always `{}`) response buffer to keep ownership
        # symmetric with admit_filing.
        if result_ptr:
            self._lib.ciris_verify_free(result_ptr)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if self._handle is None:
            raise RuntimeError(
                "ReconsiderDosGuard is closed — handle was already freed."
            )


# ---------------------------------------------------------------------------
# Wheel-side attach hook
# ---------------------------------------------------------------------------


def attach_to(cls) -> None:
    """Attach the reconsider-dos wheel surface to a class.

    Expected usage from ``ciris_verify/client.py``::

        from ._wheel_reconsider_dos import attach_to as _attach_reconsider_dos
        _attach_reconsider_dos(CIRISVerify)

    This patches the class to:

    1. Expose the :class:`ReconsiderDosGuard` constructor as
       ``CIRISVerify.new_reconsider_dos_guard``.
    2. Add a ``_wire_reconsider_dos_ffi`` instance method which sets
       ``self._has_reconsider_dos_support`` based on FFI symbol
       availability. The patched ``__init__`` calls this hook at the
       very end of construction (preserving original ``__init__``
       behavior).

    The patched ``__init__`` is idempotent — if attach_to is invoked
    twice on the same class, only the first wrap takes effect.
    """
    if getattr(cls, "_reconsider_dos_attached", False):
        return

    # ------------------------------------------------------------------
    # Patch __init__ to wire the FFI after the parent __init__ runs.
    # ------------------------------------------------------------------
    _orig_init = cls.__init__

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        # If the parent init failed to load the CDLL, leave the support
        # flag False and bail.
        if getattr(self, "_lib", None) is None:
            self._has_reconsider_dos_support = False
            return
        self._has_reconsider_dos_support = _wire_reconsider_dos_ffi(self)

    _patched_init.__doc__ = _orig_init.__doc__
    _patched_init.__name__ = _orig_init.__name__
    _patched_init.__qualname__ = _orig_init.__qualname__
    cls.__init__ = _patched_init

    # ------------------------------------------------------------------
    # Factory method on CIRISVerify.
    # ------------------------------------------------------------------
    def new_reconsider_dos_guard(self) -> ReconsiderDosGuard:
        """Construct a fresh :class:`ReconsiderDosGuard`.

        Each call mints an independent Rust-side guard with default
        thresholds (``DEFAULT_EVENT_RATE_LIMIT=10``,
        ``DEFAULT_ACTOR_BUDGET=30``, ``DEFAULT_BUDGET_WINDOW_MS=7d``,
        ``DEFAULT_HARASSMENT_CLUSTER_THRESHOLD=2.0``). Caller owns the
        returned object — let it fall out of scope to free, or call
        ``close()`` for deterministic release.

        Raises:
            RuntimeError: If the loaded libciris_verify_ffi predates
                v4.7.0 (the reconsider_dos symbols are missing).
        """
        return ReconsiderDosGuard(self)

    cls.new_reconsider_dos_guard = new_reconsider_dos_guard
    cls._wire_reconsider_dos_ffi = _wire_reconsider_dos_ffi
    cls._reconsider_dos_attached = True


# ---------------------------------------------------------------------------
# Smoke test — exercised when the module is run directly. Requires the
# loaded CDLL to expose the reconsider_dos symbols (v4.7.0+).
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # Minimal-dependency smoke test: load the CDLL directly and walk
    # the lifecycle without going through CIRISVerify (which has its
    # own initialization side-effects we don't want here).
    import os
    import sys

    HERE = os.path.dirname(os.path.abspath(__file__))
    # Prefer the in-tree-built .so over an installed wheel.
    candidates = [
        os.path.join(HERE, "libciris_verify_ffi.so"),
        os.path.join(
            HERE,
            "..",
            "..",
            "..",
            "target",
            "debug",
            "libciris_verify_ffi.so",
        ),
        os.path.join(
            HERE,
            "..",
            "..",
            "..",
            "target",
            "release",
            "libciris_verify_ffi.so",
        ),
    ]
    lib_path = next((p for p in candidates if os.path.exists(p)), None)
    if lib_path is None:
        print("[smoke] no libciris_verify_ffi.so found; build with "
              "`cargo build -p ciris-verify-ffi` first")
        sys.exit(0)

    lib = ctypes.CDLL(lib_path)
    # Also wire ciris_verify_free for buffer cleanup.
    lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
    lib.ciris_verify_free.restype = None

    # Build a stub object exposing just enough surface for
    # ReconsiderDosGuard to drive itself.
    class _Stub:
        pass

    stub = _Stub()
    stub._lib = lib
    stub._has_reconsider_dos_support = _wire_reconsider_dos_ffi(stub)
    if not stub._has_reconsider_dos_support:
        print("[smoke] FFI symbols missing — this wheel predates v4.7.0")
        sys.exit(1)

    print("[smoke] FFI symbols wired OK")

    g = ReconsiderDosGuard(stub)
    print("[smoke] guard allocated")

    T0 = 1_700_000_000_000

    d1 = g.admit_filing("evt-A", "alice", "bob", T0)
    print(f"[smoke] admit #1: {d1}")
    assert d1 == {"admitted": True}, d1

    d2 = g.admit_filing("evt-B", "alice", "bob", T0 + 1_000)
    print(f"[smoke] admit #2: {d2}")
    assert d2 == {"admitted": True}, d2

    # Third filing — harassment cluster fires.
    d3 = g.admit_filing("evt-C", "alice", "bob", T0 + 2_000)
    print(f"[smoke] admit #3: {d3}")
    assert d3["admitted"] is False
    assert "HarassmentClusterDetected" in d3["rejection"]

    # Record an outcome — no-op for this test but exercises the surface.
    g.record_outcome("evt-A", "alice", "successful")
    print("[smoke] record_outcome OK")

    # Test invalid outcome.
    try:
        g.record_outcome("evt-A", "alice", "nonsense")
    except ValueError as e:
        print(f"[smoke] invalid outcome rejected: {e}")
    else:
        print("[smoke] ERROR: invalid outcome NOT rejected")
        sys.exit(1)

    g.close()
    print("[smoke] close OK")

    # Second close is a no-op.
    g.close()
    print("[smoke] double-close OK")

    # Calling admit_filing on closed guard raises.
    try:
        g.admit_filing("evt", "alice", "bob", T0)
    except RuntimeError as e:
        print(f"[smoke] post-close call rejected: {e}")
    else:
        print("[smoke] ERROR: post-close call NOT rejected")
        sys.exit(1)

    print("[smoke] all checks passed")
