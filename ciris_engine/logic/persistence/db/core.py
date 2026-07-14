import logging
import sys
import threading
from pathlib import Path
from typing import Any, Optional, Tuple, cast

from ciris_engine.logic.config.db_paths import (
    get_audit_db_full_path,
    get_sqlite_db_full_path,
)

logger = logging.getLogger(__name__)


# Test database path override — retained as a fixture seam only. The legacy
# SQLite connection layer that consumed this (get_db_connection and friends)
# was deleted in 2.9.7 (#896): all reads + writes route through ciris-persist's
# Engine, wired per-test via `set_persist_engine()`. A handful of older test
# fixtures still save/restore this attribute; it is otherwise inert.
_test_db_path: Optional[str] = None


def initialize_database(db_path: Optional[str] = None) -> None:
    """Bootstrap the database for 2.9.0.

    Both SQLite and PostgreSQL deployments are owned end-to-end by
    ciris-persist's Engine: `_bootstrap_persist_engine` constructs the
    Engine (which runs persist's own sqlx migrations to create the
    `cirislens.*` / `cirisgraph.*` schema), then runs the A0a legacy
    graph migration once. There is no agent-side CREATE TABLE — persist's
    `run_legacy_graph_migration` (v1.6.4, CIRISPersist#70) reads any
    legacy 2.8.x `graph_nodes` / `graph_edges` over its own connection,
    and no-ops gracefully when those tables are absent (fresh install).
    """
    import traceback

    caller_info = "".join(traceback.format_stack()[-4:-1])
    logger.info(f"[DB_INIT] initialize_database called from:\n{caller_info}")

    try:
        if db_path is None:
            db_path = get_sqlite_db_full_path()
        logger.info(f"Initializing database via persist Engine: {db_path}")
        _bootstrap_persist_engine(db_path)
    except Exception as e:
        logger.exception(f"Database error during initialization: {e}")
        raise


def _persist_dsn_and_sentinel(db_path: str) -> Tuple[str, Optional[Path]]:
    """Resolve a db_path / database_url to (persist DSN, sentinel directory).

    Three supported forms — and crucially, a SQLite *URL* must never be run
    through Path().resolve(): that mangles the URL into a bogus filesystem
    path and silently bootstraps persist against the wrong (empty) database.

      - Postgres URL            -> used verbatim; sentinels in the data dir
      - SQLite URL (sqlite://)  -> used verbatim — the config schema
                                   documents sqlite://... as a valid
                                   database_url; sentinels anchored next to
                                   the db file
      - bare filesystem path    -> wrapped as sqlite:///<abs>; sentinels
                                   anchored beside the file
    """
    if db_path.startswith(("postgres://", "postgresql://")):
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        return db_path, Path(get_data_dir())
    if db_path.startswith("sqlite:"):
        # SQLAlchemy form: sqlite:///rel/path (3 slashes -> relative) or
        # sqlite:////abs/path (4 slashes -> absolute). Splitting on
        # 'sqlite:///' keeps the right leading-slash count for Path().
        path_part = (
            db_path.split("sqlite:///", 1)[-1] if "sqlite:///" in db_path else ""
        )
        sentinel = (
            Path(path_part).resolve().parent
            if path_part and path_part != ":memory:"
            else None
        )
        return db_path, sentinel
    abs_path = Path(db_path).resolve()
    # `sqlite:///{abs_path}` where abs_path begins with '/' yields
    # 'sqlite:////absolute/path' — 4 slashes, absolute as required.
    return f"sqlite:///{abs_path}", abs_path.parent


def _bootstrap_persist_engine(db_path: Optional[str]) -> None:
    """Construct the ciris-persist Engine, run A0a migration if needed,
    and wire the engine into `persistence.models.graph` (2.9.0).

    Idempotent per-process: if an Engine is already wired, this is a
    no-op. Persist's Engine holds the tokio runtime + connection pool
    and is designed for one instance per process — tests that need
    multiple isolated DBs must explicitly call set_persist_engine()
    with their own Engine instance.

    Tolerant: if persist is unavailable or migration fails, logs the
    error but does not block startup. The agent will then hit the
    "engine not initialized" RuntimeError on the first persistence call,
    surfacing the problem loud rather than silently.
    """
    import os
    from pathlib import Path

    # Compute the expected DSN up front so we can decide whether to
    # re-wire. Production calls initialize_database() once per process
    # with the same db_path — second/third calls are no-ops. Tests
    # call it with a fresh temp_db each time — those re-wire.
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    if db_path is None:
        _resolved_db_path = get_sqlite_db_full_path()
    else:
        _resolved_db_path = db_path
    if not isinstance(_resolved_db_path, str):
        _resolved_db_path = str(_resolved_db_path)
    # Same resolution the bootstrap below uses — so a sqlite:// URL produces
    # an _expected_dsn that actually matches and the idempotent-skip works.
    _expected_dsn = _persist_dsn_and_sentinel(_resolved_db_path)[0]

    if (
        graph_persistence._engine is not None
        and graph_persistence._engine_dsn == _expected_dsn
    ):
        logger.debug(
            "persist engine already wired to %s, skipping re-bootstrap", _expected_dsn
        )
        return

    # Resolve the DSN. Postgres takes its own URL; SQLite uses
    # SQLAlchemy-style sqlite:// + (3 or 4 slashes).
    if db_path is None:
        db_path = get_sqlite_db_full_path()

    if not isinstance(db_path, str):
        db_path = str(db_path)

    # Postgres URL verbatim, sqlite:// URL verbatim, bare path -> sqlite:///.
    # See _persist_dsn_and_sentinel — a sqlite:// URL must not be resolved
    # as a filesystem path.
    dsn, sentinel_dir = _persist_dsn_and_sentinel(db_path)

    signing_key_id = os.environ.get("CIRIS_AGENT_ID", "ciris-agent-bootstrap")

    try:
        from ciris_engine.logic.persistence._substrate import Engine  # one-wheel seam (#896)
    except ImportError:
        logger.warning(
            "ciris-persist not importable; 2.9.0 absorption disabled. Pin ciris-persist>=1.6.4 in requirements.txt."
        )
        return

    # Local signing seed for the persist Engine. Per persist 3.0 CHANGELOG
    # #112 ("Engine::sign_hybrid facade + cohabitation propagation fix"),
    # `local_key_id` + `local_key_path` configure a LocalSigner so the
    # agent can call `Engine::sign_hybrid` directly. The seed file holds
    # 32 raw Ed25519 bytes mode 0o600, persisted under the data dir so the
    # local identity is stable across restarts.
    #
    # NOTE — this alone does NOT close the Edge cohabitation pubkey-shape
    # mismatch (CIRISEdge#43): persist 3.0 exposes the LocalSigner's 32-
    # byte Ed25519 surface via `local_public_key_b64()` (correct), but
    # `keyring_signer_capsule()` — which Edge's ReticulumTransport reads —
    # still returns the hardware-rooted hybrid signer whose `public_key()`
    # is 65 bytes. Edge then refuses with "federation Ed25519 pubkey must
    # be 32 bytes, got 65". Tracked upstream; agent-side config below is
    # the correct shape regardless.
    from ciris_engine.logic.utils.path_resolution import get_data_dir

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    local_seed_path = data_dir / "local_signing.seed"
    if not local_seed_path.exists():
        # Bootstrap a fresh Ed25519 seed. Persist's LocalSigner reads 32
        # raw bytes from this path; matching shape is the entire interface.
        local_seed_path.write_bytes(os.urandom(32))
        try:
            local_seed_path.chmod(0o600)
        except (
            OSError
        ) as e:  # noqa: BLE001 - chmod is best-effort on platforms (Windows)
            logger.debug("Could not chmod local signing seed (non-fatal): %s", e)
        logger.info("Bootstrapped local signing seed at %s", local_seed_path)

    # PQC (post-quantum) seed for hybrid signing. Persist 3.x's
    # `Engine::sign_hybrid` (used by `audit_record_entry` on Postgres for
    # the Merkle chain) refuses to sign without a local PQC key — the
    # Ed25519-only path SQLite uses doesn't suffice. The Postgres backend
    # raises `ciris_persist.Permanent: merkle: sign_hybrid: PQC local not
    # configured (set pqc_key_id + pqc_key_path)` and the agent then can't
    # write to the audit chain, which cascades into "Hash chain data not
    # generated" handler errors and missing ACTION_RESULT events. Bootstrap
    # a 32-byte seed matching the LocalSigner contract so the persist 3.x
    # hybrid path has a key to sign with on both backends.
    local_pqc_seed_path = data_dir / "local_pqc_signing.seed"
    if not local_pqc_seed_path.exists():
        local_pqc_seed_path.write_bytes(os.urandom(32))
        try:
            local_pqc_seed_path.chmod(0o600)
        except (
            OSError
        ) as e:  # noqa: BLE001 - chmod is best-effort on platforms (Windows)
            logger.debug("Could not chmod local PQC signing seed (non-fatal): %s", e)
        logger.info("Bootstrapped local PQC signing seed at %s", local_pqc_seed_path)

    # Test isolation only: under pytest, fixtures routinely bootstrap a
    # fresh per-test engine, and a single test may invoke more than one
    # engine-wiring fixture. ciris-persist's process-singleton rejects a
    # second construction with a different config — so un-pin the current
    # engine first via reset_engine() (handle-free; CIRISPersist#88). We
    # only reach here when the idempotent-skip above did NOT fire, i.e. a
    # genuinely different config is being bootstrapped. Gated strictly on
    # PYTEST_CURRENT_TEST: in production a second differing config is a
    # real bug and persist's EngineConfigMismatch guardrail must still
    # fire untouched.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from ciris_engine.logic.persistence._substrate import reset_engine  # one-wheel seam (#896)

            reset_engine()
        except Exception:  # noqa: BLE001 - best-effort test teardown
            pass
        graph_persistence._engine = None
        graph_persistence._engine_dsn = None

    # iOS default thread stack is 512KB; persist's tokio runtime needs ~8MB
    # for its async init. Constructing Engine() directly on the asyncio
    # thread blows the stack and crashes with EXC_BAD_ACCESS / SIGBUS /
    # KERN_PROTECTION_FAILURE "Thread stack size exceeded due to excessive
    # recursion" (CIRISRuntime thread, deep frames into
    # ciris_persist.ciris_persist). Same fix CIRISVerify's iOS service.py
    # applies for the same reason. On non-iOS platforms pthread default is
    # ample (Linux 8MB, macOS-app workers ~512KB but main is large) so we
    # only pay the worker-thread cost on iOS.
    _is_ios = sys.platform == "ios" or (
        sys.platform == "darwin"
        and hasattr(sys, "implementation")
        and "iphoneos" in getattr(sys.implementation, "_multiarch", "").lower()
    )

    def _construct_engine() -> "Engine":
        return Engine(
            dsn,
            signing_key_id,
            local_key_id=signing_key_id,
            local_key_path=str(local_seed_path),
            local_pqc_key_id=signing_key_id,
            local_pqc_key_path=str(local_pqc_seed_path),
        )

    try:
        if _is_ios:
            _result: dict[str, object] = {}

            def _ios_worker() -> None:
                # Narrow to Exception so KeyboardInterrupt / SystemExit
                # propagate up the worker thread naturally instead of being
                # silently transported back to main via `_result["error"]`.
                # Exception subclasses (the only thing the persist Engine
                # constructor realistically raises — sqlx errors, FFI
                # marshalling errors, OSError on lock) are still captured
                # for re-raise on the main thread.
                try:
                    _result["engine"] = _construct_engine()
                except Exception as we:
                    _result["error"] = we

            _prev_stack = threading.stack_size()
            try:
                threading.stack_size(8 * 1024 * 1024)
                _t = threading.Thread(target=_ios_worker, name="persist-engine-init")
                _t.start()
                _t.join()
            finally:
                threading.stack_size(_prev_stack)
            if "error" in _result:
                raise _result["error"]  # type: ignore[misc]
            # cast through Any: ciris-persist's Engine has no Python type stubs
            # (the `from ciris_persist import Engine` is `type: ignore[import-untyped]`),
            # so mypy infers `_result["engine"]` as `object` from the
            # `dict[str, object]` declaration above and we lose attribute-resolution
            # downstream (e.g. `engine.run_legacy_graph_migration` at line ~1046).
            engine = cast(Any, _result["engine"])
        else:
            engine = _construct_engine()
    except Exception as e:
        # iOS: flock() returns EPERM in the sandbox. Single-process mobile app
        # has no multi-agent risk. Delete any stale lock file and retry once.
        if "operation not permitted" in str(e).lower() or "lock" in str(e).lower():
            is_ios = sys.platform == "ios" or (
                sys.platform == "darwin"
                and hasattr(sys, "implementation")
                and "iphoneos" in getattr(sys.implementation, "_multiarch", "").lower()
            )
            if is_ios:
                logger.warning(
                    "iOS: Engine bootstrap lock failed (%s) — clearing stale locks and retrying",
                    e,
                )
                # Remove any stale lock/WAL files that may be blocking
                import glob

                for pattern in [f"{db_path}*-lock", f"{db_path}-journal"]:
                    for lock_file in glob.glob(pattern):
                        try:
                            Path(lock_file).unlink()
                            logger.info("Removed stale lock: %s", lock_file)
                        except OSError as unlink_err:
                            logger.debug(
                                "Could not remove stale lock %s: %s",
                                lock_file,
                                unlink_err,
                            )
                # Retry with fresh state
                try:
                    from ciris_engine.logic.persistence._substrate import reset_engine  # one-wheel seam (#896)

                    reset_engine()
                except Exception as reset_err:
                    logger.debug(
                        "reset_engine() before retry failed (non-fatal): %s", reset_err
                    )
                engine = Engine(dsn, signing_key_id)
            else:
                raise
        else:
            raise
    logger.info("ciris-persist Engine constructed (dsn=%s)", dsn)

    # A0a graph migration + A0b audit bridge. Both run once, sentinel-gated.
    if sentinel_dir is not None:
        # A0a: copy legacy graph_nodes/graph_edges → cirisgraph.* . Persist
        # owns the whole operation since v1.6.4 (CIRISPersist#70) — it reads
        # the legacy schema over its own connection (SQLite *and* Postgres),
        # so the agent ships zero raw SQL for the upgrade path. Idempotent
        # and tolerant of legacy-tables-absent on fresh installs.
        sentinel = sentinel_dir / ".persist_migrated"
        if not sentinel.exists():
            try:
                import json as _json

                logger.info(
                    "A0a migration sentinel absent — running legacy graph migration"
                )
                raw = engine.run_legacy_graph_migration(_json.dumps({"dry_run": False}))
                stats = _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if (
                    stats.get("outcome") in ("ok", "partial")
                    and stats.get("errors", 0) == 0
                ):
                    sentinel.write_text(
                        f'{{"nodes_written":{stats.get("nodes_written", 0)},'
                        f'"edges_written":{stats.get("edges_written", 0)}}}'
                    )
                    logger.info(
                        "A0a migration complete: %d nodes, %d edges "
                        "(skipped: %d already-present, %d too-large; "
                        "%d dangling-FK edges)",
                        stats.get("nodes_written", 0),
                        stats.get("edges_written", 0),
                        stats.get("nodes_skipped_already_present", 0),
                        stats.get("nodes_skipped_too_large", 0),
                        stats.get("edges_skipped_dangling_fk", 0),
                    )
                else:
                    logger.error(
                        "A0a migration outcome=%s errors=%d; sentinel NOT written",
                        stats.get("outcome"),
                        stats.get("errors", 0),
                    )
            except Exception:
                logger.exception("A0a migration failed; persist engine wired anyway")

        # 2.9.0 A0b: bridge the legacy audit chain into persist's
        # cirislens_audit_log. Sentinel-gated like A0a; runs once on
        # first 2.9.0 boot. Tolerant: if CIRISVerify isn't ready yet
        # (early-boot ordering) or if the legacy audit DB is absent
        # (fresh deployment with no legacy chain), log + skip.
        audit_sentinel = sentinel_dir / ".audit_bridged"
        # Resolve the legacy audit DB from config (database.audit_db) so a
        # deployment that customised audit_db still bridges its chain —
        # don't assume the default sentinel_dir/ciris_audit.db location.
        try:
            legacy_audit_db = Path(get_audit_db_full_path())
        except Exception:  # pragma: no cover - defensive
            legacy_audit_db = sentinel_dir / "ciris_audit.db"
        if not audit_sentinel.exists() and legacy_audit_db.exists():
            try:
                # Bundled under ciris_engine/ so the in-place upgrade path is
                # reachable from Chaquopy on Android too — tools/ isn't in
                # the mobile extractPackages list (CIRISAgent#780).
                from ciris_engine.logic.audit.chain_bridge import run as run_bridge

                logger.info("A0b audit-bridge sentinel absent — running chain bridge")
                result = run_bridge(
                    engine_db=Path(db_path),
                    audit_db=legacy_audit_db,
                    dry_run=False,
                    engine=engine,
                )
                audit_sentinel.write_text(
                    f'{{"bridge_id":"{result.bridge_id}",'
                    f'"legacy_terminal_seq":{result.legacy_terminal_seq},'
                    f'"legacy_db_sha256":"{result.legacy_db_sha256}"}}'
                )
                logger.info(
                    "A0b audit bridge complete: legacy_seq=%d bridge_id=%s",
                    result.legacy_terminal_seq,
                    result.bridge_id,
                )
            except Exception:
                # CIRISVerify availability + signing-key access are
                # ordering-sensitive at boot; we don't block startup on
                # bridge failure. Next boot retries (sentinel absent).
                logger.exception("A0b audit bridge failed; persist engine wired anyway")
        elif not legacy_audit_db.exists():
            logger.debug(
                "no legacy audit DB at %s — fresh deployment, no chain to bridge",
                legacy_audit_db,
            )

    # Wire the engine into persistence.models.graph.
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    graph_persistence.set_persist_engine(engine, dsn)
