import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, cast

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path

logger = logging.getLogger(__name__)


# Test database path override — retained as a fixture seam only. The legacy
# SQLite connection layer that consumed this (get_db_connection and friends)
# was deleted in 2.9.7 (#896): all reads + writes route through ciris-persist's
# Engine, wired per-test via `set_persist_engine()`. A handful of older test
# fixtures still save/restore this attribute; it is otherwise inert.
_test_db_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# #937 — bounded, loud database init.
#
# The failure this guards: agent boot calls `initialize_database`
# synchronously from `LocalGraphMemoryService.__init__`
# (services/graph/memory_service.py:67), which blocks the asyncio event
# loop inside persist's `Engine(...)` constructor. That constructor does
# `connect + run_migrations` under a Postgres session-scoped
# `pg_advisory_lock` (CIRISPersist src/store/postgres.rs:1153), and every
# wait in that path is UNBOUNDED. On a shared `ciris_db` another tenant's
# long-running statement holding a conflicting table lock stalls the
# migration DDL for as long as it runs — 15 minutes in the #937 report —
# with zero agent-side log output, because persist logs through Rust
# `tracing` which the agent never initializes.
#
# Three bounds, all named + env-overridable:
#
#   1. `CIRIS_DB_INIT_TIMEOUT_SECONDS` — wall-clock ceiling on the whole
#      Engine bootstrap. Exceeding it raises `DatabaseInitializationTimeout`
#      (a TimeoutError) which propagates through `initialize_database` to
#      the initialization service, failing the DATABASE phase loudly
#      instead of pretending to boot.
#   2. `CIRIS_DB_INIT_LOCK_TIMEOUT` — Postgres session `lock_timeout` on
#      the startup connection, delivered as a libpq `options` DSN
#      parameter. Bounds any single lock acquisition in the migration
#      path (both the DDL locks and the `pg_advisory_lock` wait).
#   3. `CIRIS_DB_INIT_STATEMENT_TIMEOUT` — Postgres session
#      `statement_timeout`, default `0` (disabled).
#
# ── Why these defaults, and the multi-occurrence constraint ──
#
# CIRIS supports N occurrences sharing one database. They all boot
# through this path, and persist serializes them on ONE global advisory
# lock: the leader runs migrations, every follower BLOCKS inside
# `pg_advisory_lock` until the leader's session closes. `lock_timeout`
# applies to advisory locks, so a too-aggressive value would kill
# followers during a legitimate cold-start migration. The defaults are
# therefore deliberately generous — they exist to convert a 15-minute
# silent hang into a bounded loud failure, NOT to police normal
# contention. In steady state (schema at head) the leader's work is
# sub-second and followers wait about as long.
#
# `statement_timeout` defaults to disabled because aborting a legitimate
# long migration or backfill mid-flight is a worse failure than the hang
# it would prevent; the wall-clock bound already covers that case.
# Operators with a known-fast migration set can opt in.
# NOTE — every default below is JUDGEMENT, not measurement. Nobody has yet
# timed a cold migration against a production-sized shared database; these
# were chosen to survive N-occurrence cold-start serialization with room to
# spare, not fitted to observed data. Do not cite them as empirical. If you
# measure a real cold-migration wall time, set them from it and delete this
# note.
DB_INIT_TIMEOUT_ENV = "CIRIS_DB_INIT_TIMEOUT_SECONDS"
DB_INIT_TIMEOUT_SECONDS_DEFAULT = 300.0

DB_INIT_PROGRESS_INTERVAL_SECONDS = 15.0

DB_INIT_LOCK_TIMEOUT_ENV = "CIRIS_DB_INIT_LOCK_TIMEOUT"
DB_INIT_LOCK_TIMEOUT_DEFAULT = "120s"

DB_INIT_STATEMENT_TIMEOUT_ENV = "CIRIS_DB_INIT_STATEMENT_TIMEOUT"
DB_INIT_STATEMENT_TIMEOUT_DEFAULT = "0"  # 0 = disabled

# Paste-ready operator diagnostic, embedded verbatim in the timeout error.
# psycopg2 is dev-only (requirements-dev.txt) so production cannot run this
# itself; naming the query is the honest, dependency-free alternative.
PG_BLOCKER_DIAGNOSTIC_SQL = (
    "SELECT a.pid, a.state, age(clock_timestamp(), a.query_start) AS age, "
    "pg_blocking_pids(a.pid) AS blocked_by, a.query "
    "FROM pg_stat_activity a WHERE a.datname = current_database() "
    "AND a.state <> 'idle' ORDER BY a.query_start;"
)


class DatabaseInitializationTimeout(TimeoutError):
    """The persist Engine bootstrap exceeded its wall-clock budget.

    Raised out of `initialize_database` so the DATABASE initialization
    phase fails visibly. A bounded loud failure beats an unbounded
    silent hang (#937).
    """


def _redact_dsn(dsn: str) -> str:
    """Strip credentials from a DSN so it is safe to log.

    `postgresql://user:s3cret@host:5432/db?x=y` -> `postgresql://user:***@host:5432/db`
    SQLite DSNs have no credentials and pass through unchanged apart from
    their query string.
    """
    if "://" not in dsn:
        return dsn
    scheme, _, rest = dsn.partition("://")
    rest = rest.split("?", 1)[0]
    if "@" in rest:
        userinfo, _, hostpart = rest.rpartition("@")
        user = userinfo.split(":", 1)[0]
        rest = f"{user}:***@{hostpart}"
    return f"{scheme}://{rest}"


def _is_postgres_dsn(dsn: str) -> bool:
    return dsn.startswith(("postgres://", "postgresql://"))


def _db_init_timeout_seconds() -> float:
    """Wall-clock ceiling for the Engine bootstrap, in seconds.

    A non-positive value disables the bound (escape hatch for an operator
    running a genuinely multi-hour first migration).
    """
    import os

    raw = os.environ.get(DB_INIT_TIMEOUT_ENV, "")
    if not raw:
        return DB_INIT_TIMEOUT_SECONDS_DEFAULT
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not a number — falling back to %.0fs",
            DB_INIT_TIMEOUT_ENV,
            raw,
            DB_INIT_TIMEOUT_SECONDS_DEFAULT,
        )
        return DB_INIT_TIMEOUT_SECONDS_DEFAULT


def _startup_lock_options() -> str:
    """Build the libpq `options` value carrying the startup session GUCs.

    Returns an empty string when both knobs are disabled.
    """
    import os

    lock_timeout = os.environ.get(DB_INIT_LOCK_TIMEOUT_ENV, DB_INIT_LOCK_TIMEOUT_DEFAULT).strip()
    statement_timeout = os.environ.get(DB_INIT_STATEMENT_TIMEOUT_ENV, DB_INIT_STATEMENT_TIMEOUT_DEFAULT).strip()

    parts = []
    if lock_timeout and lock_timeout != "0":
        parts.append(f"-c lock_timeout={lock_timeout}")
    if statement_timeout and statement_timeout != "0":
        parts.append(f"-c statement_timeout={statement_timeout}")
    return " ".join(parts)


def _with_startup_timeouts(dsn: str) -> str:
    """Attach `lock_timeout` / `statement_timeout` to a Postgres startup DSN.

    Postgres only — a SQLite DSN is returned untouched (SQLite has no
    session GUCs and persist's SQLite backend would reject the parameter).

    Why the DSN is the lever: persist owns both connections it opens, and
    the agent never sees either. But
    `PostgresBackend::dedicated_connect` — the connection that holds the
    migration advisory lock and runs every DDL statement — passes the
    DSN string through verbatim to `tokio_postgres::connect`
    (CIRISPersist src/store/postgres.rs:306 stores it, :613/:650 use it),
    and tokio-postgres honours the libpq `options` keyword. So the DSN
    IS the agent-side seam into persist's startup session.

    Scope is exactly right: the pooled runtime connections are built from
    a deadpool `Config` that copies only host/port/user/password/dbname
    (postgres.rs:249-264), so `options` is dropped there. These GUCs
    apply to the migration phase and nothing else.

    An operator-supplied `options` in the DSN always wins — we never
    override an explicit choice.
    """
    if not _is_postgres_dsn(dsn):
        return dsn

    from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

    parts = urlsplit(dsn)
    if any(key == "options" for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
        logger.debug("DSN already carries libpq `options` — leaving it untouched")
        return dsn

    options = _startup_lock_options()
    if not options:
        return dsn

    # Percent-encode, never form-encode. tokio-postgres decodes URL query
    # values with `percent_decode` only (config.rs:1162) — a `+` stays a
    # literal `+` and would corrupt the options string into
    # `-c+lock_timeout=120s`, which Postgres rejects. libpq behaves the
    # same way. So: `%20` for the separator, `%3D` for the `=`.
    encoded = quote(options, safe="")
    # Append to the raw query rather than round-tripping the existing
    # params through parse_qsl/urlencode — re-encoding an operator's DSN
    # (e.g. a password-bearing `sslmode`/`options` sibling) risks changing
    # bytes we were not asked to touch.
    query = f"{parts.query}&options={encoded}" if parts.query else f"options={encoded}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _blocker_hint(dsn: str) -> str:
    """Best-effort explanation of what is holding the startup lock.

    Production does not ship a Postgres driver (psycopg2 is dev-only, see
    requirements-dev.txt), so this degrades to naming the exact query an
    operator should run. When psycopg2 IS importable (dev, QA, tooling)
    the probe runs and the blocking pid/query lands in the error itself.
    """
    if not _is_postgres_dsn(dsn):
        return ""

    try:
        # Imported dynamically on purpose: psycopg2 is dev-only, so a static
        # import would need a `type: ignore` that is "unused" in every
        # environment that DOES have the stubs and required in every one that
        # does not. importlib is correct in both, and `ModuleNotFoundError`
        # is an `ImportError` so the except below still catches its absence.
        import importlib

        psycopg2: Any = importlib.import_module("psycopg2")

        # Independent connection with its own hard timeouts — the
        # diagnostic must never become a second hang.
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '5s'")
                cur.execute(PG_BLOCKER_DIAGNOSTIC_SQL)
                rows = cur.fetchall()
        finally:
            conn.close()
        if rows:
            rendered = "; ".join(
                f"pid={r[0]} state={r[1]} age={r[2]} blocked_by={r[3]} query={str(r[4])[:200]}" for r in rows
            )
            return f" Active backends: {rendered}."
    except Exception as probe_err:  # noqa: BLE001 - diagnostics are best-effort
        logger.debug("pg_stat_activity blocker probe unavailable: %s", probe_err)

    return " To identify the blocker, run against the same database: " f"{PG_BLOCKER_DIAGNOSTIC_SQL}"


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
    import time
    import traceback

    caller_info = "".join(traceback.format_stack()[-4:-1])
    logger.info(f"[DB_INIT] initialize_database called from:\n{caller_info}")

    started = time.monotonic()
    try:
        if db_path is None:
            db_path = get_sqlite_db_full_path()
        # #937 — never log a raw DSN: it carries the Postgres password.
        logger.info(
            "[DB_INIT] phase=bootstrap begin target=%s timeout=%.0fs",
            _redact_dsn(db_path),
            _db_init_timeout_seconds(),
        )
        _bootstrap_persist_engine(db_path)
        logger.info(
            "[DB_INIT] phase=bootstrap complete target=%s elapsed=%.1fs",
            _redact_dsn(db_path),
            time.monotonic() - started,
        )
    except Exception as e:
        logger.exception(
            "[DB_INIT] phase=bootstrap FAILED target=%s elapsed=%.1fs: %s",
            _redact_dsn(db_path) if db_path else "<unresolved>",
            time.monotonic() - started,
            e,
        )
        raise


def _persist_dsn_and_sentinel(db_path: str) -> Tuple[str, Optional[Path]]:
    """Resolve a db_path / database_url to (persist DSN, sentinel directory).

    Three supported forms — and crucially, a SQLite *URL* must never be run
    through Path().resolve(): that mangles the URL into a bogus filesystem
    path and silently bootstraps persist against the wrong (empty) database.

      - Postgres URL            -> startup lock/statement timeouts attached
                                   (#937); sentinels in the data dir
      - SQLite URL (sqlite://)  -> used verbatim — the config schema
                                   documents sqlite://... as a valid
                                   database_url; sentinels anchored next to
                                   the db file
      - bare filesystem path    -> wrapped as sqlite:///<abs>; sentinels
                                   anchored beside the file

    #937 — the Postgres `options` decoration MUST happen here, in the one
    canonical resolver, not at the call site. `_bootstrap_persist_engine`
    compares the resolved DSN against `graph_persistence._engine_dsn` for
    its idempotent-skip, and persist fingerprints the DSN for its
    process-singleton guard. Decorating in only one of those places would
    make the second `initialize_database()` call of a process see a
    "different" DSN and trip persist's `EngineConfigMismatch`.
    """
    if db_path.startswith(("postgres://", "postgresql://")):
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        return _with_startup_timeouts(db_path), Path(get_data_dir())
    if db_path.startswith("sqlite:"):
        # SQLAlchemy form: sqlite:///rel/path (3 slashes -> relative) or
        # sqlite:////abs/path (4 slashes -> absolute). Splitting on
        # 'sqlite:///' keeps the right leading-slash count for Path().
        path_part = db_path.split("sqlite:///", 1)[-1] if "sqlite:///" in db_path else ""
        sentinel = Path(path_part).resolve().parent if path_part and path_part != ":memory:" else None
        return db_path, sentinel
    abs_path = Path(db_path).resolve()
    # `sqlite:///{abs_path}` where abs_path begins with '/' yields
    # 'sqlite:////absolute/path' — 4 slashes, absolute as required.
    return f"sqlite:///{abs_path}", abs_path.parent


def _construct_engine_bounded(construct: Callable[[], Any], dsn: str, bump_stack: bool = False) -> Any:
    """Run persist's blocking Engine constructor under a wall-clock bound.

    Three properties #937 needs and the previous inline call lacked:

    * **Bounded.** The main thread joins with a deadline. On expiry we
      raise `DatabaseInitializationTimeout` rather than blocking the
      asyncio event loop forever.
    * **Loud.** Every `DB_INIT_PROGRESS_INTERVAL_SECONDS` a WARNING lands
      naming the phase, the redacted target and the elapsed time, so
      "the log did not advance by a single line for 15 minutes" cannot
      happen again. persist's own `tracing::info!("migration phase
      begin")` is invisible to us — the agent never calls `init_tracing()`
      — so this is the only progress signal that exists.
    * **Diagnostic.** The timeout message carries the blocking pid/query
      when a driver is available, and otherwise the exact query to run.

    `bump_stack` raises the worker's stack to 8 MB — iOS's default 512 KB
    is too small for persist's tokio runtime init (see caller).

    The worker is a daemon: a wedged FFI call cannot be cancelled from
    Python, so on timeout we abandon it rather than block process exit.
    """
    import time

    result: dict[str, object] = {}

    def _worker() -> None:
        # Narrow to Exception so KeyboardInterrupt / SystemExit propagate
        # up the worker thread naturally instead of being silently
        # transported back to main via `result["error"]`. Exception
        # subclasses (the only thing the persist Engine constructor
        # realistically raises — sqlx errors, FFI marshalling errors,
        # OSError on lock) are still captured for re-raise on the main
        # thread.
        try:
            result["engine"] = construct()
        except Exception as we:
            result["error"] = we

    budget = _db_init_timeout_seconds()
    redacted = _redact_dsn(dsn)
    started = time.monotonic()

    prev_stack = threading.stack_size()
    try:
        if bump_stack:
            threading.stack_size(8 * 1024 * 1024)
        worker = threading.Thread(target=_worker, name="persist-engine-init", daemon=True)
        worker.start()
    finally:
        threading.stack_size(prev_stack)

    while True:
        worker.join(DB_INIT_PROGRESS_INTERVAL_SECONDS)
        elapsed = time.monotonic() - started
        if not worker.is_alive():
            break
        logger.warning(
            "[DB_INIT] phase=engine-construct still running after %.0fs "
            "(target=%s, budget=%s). persist is inside connect + migrations; "
            "on a shared database this is either another tenant holding a "
            "conflicting table lock or another occurrence holding persist's "
            "migration advisory lock.",
            elapsed,
            redacted,
            f"{budget:.0f}s" if budget > 0 else "unbounded",
        )
        if budget > 0 and elapsed >= budget:
            raise DatabaseInitializationTimeout(
                f"persist Engine construction exceeded {budget:.0f}s "
                f"(elapsed {elapsed:.0f}s) for target={redacted}. The agent is "
                f"blocked in persist's connect + migration phase and will not "
                f"finish booting.{_blocker_hint(dsn)} "
                f"Raise {DB_INIT_TIMEOUT_ENV} if this database legitimately "
                f"needs longer to migrate."
            )

    if "error" in result:
        raise cast(BaseException, result["error"])
    # cast through Any: ciris-persist's Engine has no Python type stubs (the
    # `from ciris_persist import Engine` is `type: ignore[import-untyped]`),
    # so mypy infers `result["engine"]` as `object` from the `dict[str,
    # object]` declaration above and we lose attribute resolution downstream
    # (e.g. `engine.run_legacy_graph_migration`).
    return cast(Any, result["engine"])


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

    if graph_persistence._engine is not None and graph_persistence._engine_dsn == _expected_dsn:
        logger.debug("persist engine already wired to %s, skipping re-bootstrap", _expected_dsn)
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

    # Shared with node_fold's `_resolve_key_id()` — this same string is the
    # node's `keystore_alias`, and the sealed keystore keys off (dir, alias).
    from ciris_engine.logic.utils.path_resolution import get_federation_alias

    signing_key_id = get_federation_alias()

    # #937 — safety net. `setup_basic_logging` normally installs this, but
    # not every entry point (tests, tooling, embedded hosts) goes through it,
    # and the migration-phase logs we most need are emitted by the very next
    # call. Idempotent, so the usual double-call costs nothing.
    from ciris_engine.logic.utils.substrate_logging import install_substrate_tracing

    install_substrate_tracing()

    try:
        from ciris_engine.logic.persistence._substrate import Engine  # one-wheel seam (#896)
    except ImportError:
        logger.warning(
            "ciris-persist not importable; 2.9.0 absorption disabled. Pin ciris-persist>=1.6.4 in requirements.txt."
        )
        return

    # ONE federation identity per node (CIRISServer#380 / CIRISPersist#616).
    #
    # We used to mint our own bare Ed25519 + ML-DSA-65 pair under the data dir
    # and hand the paths to `local_key_path` / `local_pqc_key_path`. That was
    # the only shape the Python constructor accepted — and it was a second
    # identity. The node's compose resolves its federation key from the sealed
    # keystore at `<home>/identity`, so the Engine signed as one key while the
    # node published as another: the self identity-occurrence failed its own
    # scrub-signature, no peer could seal to us, KEX never became authoritative,
    # and traces were produced perfectly and delivered nowhere — with ZERO
    # arrivals and ZERO rejections upstream, because nothing was attributable.
    #
    # ciris-server 0.5.161 (persist v30.4.1) closes it: pass `identity_dir` +
    # `keystore_alias` and the Engine resolves the node's own identity — sealed
    # classical half via the keystore, bare `ml_dsa_65.seed` for the PQC half
    # (no TPM does ML-DSA). We hand over no key material at all. The alias must
    # match what node_fold passes to `serve_with_python_adapter`; both read
    # `get_federation_alias()` so they cannot drift.
    #
    # `local_*_path` still exists for tests and harnesses. It must not be used
    # here: 0.5.160+ refuses to boot when the two halves are different keys.
    from ciris_engine.logic.utils.path_resolution import get_identity_dir

    identity_dir = get_identity_dir()
    identity_dir.mkdir(parents=True, exist_ok=True)

    # The PQC half must EXIST BEFORE the Engine is constructed.
    #
    # `create_identity_if_missing=True` mints only the CLASSICAL half — on a
    # virgin identity dir it writes `<alias>.ed25519.seed.blob` + `.master.key`
    # and nothing else. Verified against 0.5.161:
    #
    #     Engine(..., identity_dir=<fresh>, create_identity_if_missing=True)
    #     -> ciris-agent-bootstrap.ed25519.seed.blob   (60 B)
    #        ciris-agent-bootstrap.master.key          (32 B)
    #        ml_dsa_65.seed                            ABSENT
    #
    # Without the PQC half, persist's `sign_hybrid` — which `audit_record_entry`
    # uses for the Merkle chain — refuses to sign. The agent then cannot write
    # the audit chain, which cascades exactly as it always did: "Failed to add
    # to persist audit chain" -> "Hash chain data not generated for action
    # speak" -> no ACTION_RESULT events -> no traces captured at all.
    #
    # That cascade is invisible on any machine that has booted before, because
    # the node's compose adopts (and on its own path creates) this seed — so a
    # developer's identity dir already has it while a fresh CI checkout does
    # not. It cost a green local run and a red CI.
    #
    # Minting it here is not a second identity: the PQC half is bare BY DESIGN
    # (no TPM does ML-DSA), it lives at the conventional path the node's compose
    # reads, and compose logs `adopted existing ML-DSA-65 federation seed` from
    # exactly this file. One key, written by whichever half starts first.
    pqc_seed_path = identity_dir / "ml_dsa_65.seed"
    if not pqc_seed_path.exists():
        pqc_seed_path.write_bytes(os.urandom(32))
        try:
            pqc_seed_path.chmod(0o600)
        except OSError as e:  # noqa: BLE001 - chmod is best-effort (Windows)
            logger.debug("Could not chmod PQC seed (non-fatal): %s", e)
        logger.info("Minted the node's ML-DSA-65 federation seed at %s", pqc_seed_path)

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
        # SCRUBBER (CIRISServer#418, CIRISAgent#11). `scrubber=None` — the
        # constructor default we used to take — installs persist's NullScrubber,
        # which redacts NOTHING and, since persist v32.1.0, has its full_traces
        # batches REFUSED outright:
        #
        #     ValueError: ('scrub_treatment_mismatch', 'label=full_traces ...')
        #
        # The binding has been on every supported pin since ciris-server 0.5.174
        # and is present in the 0.5.176 we pin (verified against the wheel:
        # `ciris_server.egress_scrub`, and Engine's third parameter is
        # `scrubber`). The crate's scrubber was already wired into both RUST
        # ingest paths; the agent reaches persist through PYTHON, so it alone
        # never saw one. This closes that gap rather than changing the design.
        #
        # Imported defensively: an older pin without the symbol must degrade to
        # the previous behaviour (refused full_traces) rather than fail to boot.
        scrubber = None
        try:
            from ciris_server import egress_scrub as scrubber  # type: ignore[no-redef, import-untyped, unused-ignore]
        except ImportError:
            logger.warning(
                "ciris_server.egress_scrub unavailable on this pin — persist will install NullScrubber "
                "and full_traces batches will be refused (CIRISServer#418)"
            )

        return Engine(
            dsn,
            signing_key_id,
            scrubber=scrubber,
            identity_dir=str(identity_dir),
            keystore_alias=signing_key_id,
            # First provisioning mints the node's ONE identity. persist warns
            # that this flag is how CIRISAgent#1009 happened, so it is worth
            # being explicit about why it is safe *here* and not there:
            #
            #  - #1009 minted a SECOND identity beside an existing one, because
            #    the Engine and the node resolved different key material. Now
            #    both resolve the same (identity_dir, alias) — from
            #    get_identity_dir() / get_federation_alias() — so a mint can
            #    only ever produce the identity the node itself will then open.
            #  - We are the node. The Engine is constructed before the node's
            #    compose runs, so on a genuinely unprovisioned home nothing else
            #    can create it first; without this the first boot cannot start.
            #  - If the home moves, both halves move together: the node gets a
            #    new identity, not a split one, and the mesh re-roots it.
            #
            # The two-identity case this cannot cause is still covered by the
            # 0.5.160 boot gate, which compares public key bytes.
            create_identity_if_missing=True,
        )

    # macOS Secure Enclave session gate (CIRISServer#380). The federation
    # keystore is opened here (the Engine) and again by the node's compose in
    # `serve_with_python_adapter`. On a macOS console session whose screen is
    # LOCKED, the Secure Enclave is only intermittently reachable, so those two
    # opens can seal DIFFERENT keys under one alias and the node refuses to boot
    # with "TWO FEDERATION IDENTITIES IN ONE NODE". Block here until SE is
    # deterministically reachable (unlocked session → use SE) or consistently
    # unavailable (headless → software-only is deterministic). No-op off macOS,
    # and on iOS (which reaches its Secure Enclave reliably in the foreground).
    from ciris_engine.logic.runtime.se_session_gate import await_secure_enclave_session

    await_secure_enclave_session()

    try:
        # #937 — ALWAYS construct on a worker thread, not just on iOS.
        # The thread was originally an iOS stack-size workaround; it is now
        # also the only way to bound a blocking FFI call from Python. The
        # main thread joins with a deadline, logs progress while it waits,
        # and raises DatabaseInitializationTimeout if the budget is spent.
        engine = cast(Any, _construct_engine_bounded(_construct_engine, dsn, bump_stack=_is_ios))
    except DatabaseInitializationTimeout:
        # #937 — MUST precede the stale-lock heuristic below. That heuristic
        # is a substring match on "lock", and the timeout message says
        # "blocked"/"pg_blocking_pids" — both of which contain "lock". A
        # timeout is never a stale-lockfile condition, and retrying a
        # bootstrap that just burned its whole budget doubles the outage.
        raise
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
                    logger.debug("reset_engine() before retry failed (non-fatal): %s", reset_err)
                # Bounded on the retry too — a wedged retry is the same
                # unbounded hang wearing a different hat (#937).
                engine = cast(
                    Any,
                    _construct_engine_bounded(lambda: Engine(dsn, signing_key_id), dsn, bump_stack=True),
                )
            else:
                raise
        else:
            raise
    # #937 — redacted: the raw DSN carries the Postgres password.
    logger.info("ciris-persist Engine constructed (dsn=%s)", _redact_dsn(dsn))

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

                logger.info("A0a migration sentinel absent — running legacy graph migration")
                raw = engine.run_legacy_graph_migration(_json.dumps({"dry_run": False}))
                stats = _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if stats.get("outcome") in ("ok", "partial") and stats.get("errors", 0) == 0:
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

        # 2.9.7 (second-signer removal): the A0b legacy audit-chain bridge is
        # GONE. It signed its genesis entry with the deleted CIRISVerify
        # "agent-{sha12}" identity; pre-2.9.0 installs must upgrade through
        # a 2.9.x release that still ships the bridge before landing here.

    # Wire the engine into persistence.models.graph.
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    graph_persistence.set_persist_engine(engine, dsn)
