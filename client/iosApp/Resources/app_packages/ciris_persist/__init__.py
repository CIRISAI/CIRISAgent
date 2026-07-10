"""ciris_persist — unified Rust persistence for the CIRIS Trinity.

Mission alignment: see ``MISSION.md``. This Python package is a thin
wrapper over the Rust crate; the FastAPI handler in CIRISLens calls
``Engine.receive_and_persist(bytes)`` per FSD §3.5.

Phase 1 surface:

>>> import ciris_persist as cp
>>> engine = cp.Engine(dsn="postgres://lens:lens@localhost:5432/cirislens")
>>> engine.register_public_key("agent-8a0b70302aae", b64_encoded_pubkey)
>>> summary = engine.receive_and_persist(request_body_bytes)
>>> summary["trace_events_inserted"]
8

Optional scrubber callable (Phase 1.5 contract):

>>> def my_scrubber(envelope: dict) -> tuple[dict, int]:
...     # mutate envelope, return (envelope, modified_count)
...     return envelope, 0
>>> engine = cp.Engine(dsn="...", scrubber=my_scrubber)

The scrubber MUST NOT alter ``trace_schema_version`` /
``trace_level`` / the ``events[]`` count or discriminants — the
Engine rejects schema-altering scrubber output.
"""

from .ciris_persist import (
    Conflict,
    Engine,
    EngineClosed,
    EngineConfigMismatch,
    EngineUsedAcrossFork,
    LensQueryError,
    NotFound,
    Permanent,
    PersistError,
    SUPPORTED_SCHEMA_VERSIONS,
    Transient,
    __version__,
    reset_engine,
)

__all__ = [
    "Conflict",
    "Engine",
    # v1.6.8 (CIRISPersist#75-78) — engine-lifecycle exceptions.
    "EngineClosed",
    "EngineConfigMismatch",
    "EngineUsedAcrossFork",
    "LensQueryError",
    "NotFound",
    "Permanent",
    "PersistError",
    "SUPPORTED_SCHEMA_VERSIONS",
    "Transient",
    "__version__",
    # v1.10.1 (CIRISPersist#88) — handle-free process-singleton reset.
    "reset_engine",
]

# v3.12.2 (CIRISPersist#156) — diagnostic harness surface. Re-exported
# only when the underlying Rust wheel was built with `--features
# debug-tools`; release wheels (default) don't have these symbols on
# the native module, so the import falls through silently.
#
# Harnesses test with `if hasattr(ciris_persist, "panic_count"):`
# before invoking. The full opt-in chain remains:
#   1. wheel built with `--features debug-tools`  (compile-time)
#   2. CIRIS_PERSIST_PANIC_LOG exported            (runtime)
#   3. caller invokes panic_count() / install_panic_logger()
try:
    from .ciris_persist import (  # type: ignore[attr-defined]
        install_panic_logger,
        panic_count,
    )

    __all__.extend(["install_panic_logger", "panic_count"])
except ImportError:
    # Release wheel — no debug-tools feature. The diagnostic surface
    # is genuinely absent, and that's the intended security posture.
    pass
