"""Type stubs for the Rust-built ``ciris_persist`` extension module.

Mission alignment (PLATFORM_ARCHITECTURE.md §3.5): mypy / pyright
support is part of the Phase 1 surface — the lens FastAPI codebase
already runs strict type checking, and these stubs keep ciris-persist
inside that envelope.
"""

from typing import Any, Callable, TypedDict

__version__: str
SUPPORTED_SCHEMA_VERSIONS: list[str]

class LensQueryError(Exception):
    """v0.5.3+ (CIRISPersist#27) — typed exception raised when a Rust
    panic crosses the FFI boundary. Subclasses ``Exception`` (not
    ``BaseException``) so uvicorn's ``try: except Exception:`` catches
    it as a normal 500. The original panic message is preserved as
    ``"rust_panic: <message>"`` in the exception's str form.
    """

class BatchSummary(TypedDict):
    """Result shape from :meth:`Engine.receive_and_persist`."""
    envelopes_processed: int
    trace_events_inserted: int
    trace_events_conflicted: int
    trace_llm_calls_inserted: int
    scrubbed_fields: int
    signatures_verified: int

ScrubberCallable = Callable[[dict[str, Any]], tuple[dict[str, Any], int]]

class Engine:
    """Process-singleton handle to the Rust persistence pipeline.

    v1.6.8 (CIRISPersist#75-78): the tokio runtime + connection pool
    are built **exactly once per process**. Constructing ``Engine``
    again with the same config returns a cheap handle to the
    existing engine — no second runtime. A different config raises
    :class:`EngineConfigMismatch`.

    In-process cohabitation contract (CIRIS 3.0 — agent + NodeCore +
    LensCore in one process):

    - One owner constructs ``Engine(...)`` first; adapters attach by
      constructing with the **same** config.
    - The owner calls :meth:`close` at shutdown; adapters do not.
      Use after :meth:`close` raises :class:`EngineClosed`.
    - Construct ``Engine`` **after** all forking is done — a tokio
      runtime does not survive ``fork()``. Use across a fork raises
      :class:`EngineUsedAcrossFork`.

    See ``docs/COHABITATION.md`` for the full doctrine.
    """

    def __init__(self, dsn: str, scrubber: ScrubberCallable | None = None) -> None: ...

    def close(self, force: bool = False) -> None:
        """v1.6.8 (CIRISPersist#77) — deterministic teardown.

        Flips the process-singleton's closed flag (every ``Engine``
        handle shares it) and clears the global slot so a later
        ``Engine(...)`` rebuilds. Idempotent. Only the lifecycle
        owner should call this; in-process adapters attach and
        detach but never close. After ``close()`` every method
        raises :class:`EngineClosed`.

        v1.7.0 (CIRISPersist#80): refuses with ``RuntimeError`` if
        any consumer is still registered (see
        :meth:`register_consumer`). Pass ``force=True`` to close
        regardless — for a hard process shutdown.
        """

    @property
    def is_closed(self) -> bool:
        """v1.6.8 — ``True`` once :meth:`close` has run on this
        engine (or any handle sharing its singleton cell)."""

    def engine_handle(self) -> Engine:
        """v1.7.0 (CIRISPersist#79) — return a fresh handle to the
        process-singleton engine.

        Cheap ``Arc``-clone — shares the runtime, pool, signer,
        closed flag, and consumer registry. The lifecycle owner uses
        this to hand the engine to an in-process adapter (NodeCore,
        LensCore) explicitly ("injected engine, first parameter")
        without the adapter needing the DSN / signing key.
        """

    def register_consumer(
        self, name: str, substrates: list[str] | None = None
    ) -> None:
        """v1.7.0 (CIRISPersist#80) — register an attached consumer.

        In-process adapters call this on bring-up. ``substrates``
        declares the substrate families the consumer owns (e.g.
        ``["cirisnode"]``). Idempotent — re-registering an existing
        ``name`` updates its substrate list. While any consumer is
        registered, :meth:`close` refuses without ``force=True``.

        v1.7.4 (CIRISPersist#82) — each declared substrate name is
        validated against the known persist substrate-family set
        (``cirislens``, ``cirislens_secrets``, ``cirislens_derived``,
        ``cirisgraph``, ``cirisnode``); an unknown name raises
        ``ValueError``.

        v1.7.5 — ``name`` longer than 256 bytes raises ``ValueError``;
        registering a new consumer when the shared registry already
        holds 64 raises ``RuntimeError`` (a leak guard). Registering
        on a closed engine raises ``EngineClosed``.
        """

    def substrate_owner(self, substrate: str) -> str | None:
        """v1.7.4 (CIRISPersist#82) — name of the registered consumer
        that declared ownership of ``substrate``, or ``None`` if none
        does. Cooperative, advisory check — persist does not hard-
        reject foreign writes under the singleton engine. If multiple
        consumers declared it, the lexicographically-first name wins.
        """

    def deregister_consumer(self, name: str) -> bool:
        """v1.7.0 (CIRISPersist#80) — deregister a consumer on its
        teardown. Returns ``True`` if it was registered. Idempotent.
        """

    def list_consumers(self) -> str:
        """v1.7.0 (CIRISPersist#80) — JSON snapshot of the attached-
        consumer registry: ``{name: {"substrates": [...],
        "registered_at": "<rfc3339>"}}``. Diagnostics — "who is
        using persist right now."
        """

    @property
    def consumer_count(self) -> int:
        """v1.7.0 (CIRISPersist#80) — number of registered
        consumers. :meth:`close` (without ``force``) refuses while
        this is non-zero."""

    # ── v1.9.0 (CIRISPersist#84) — change-feed / subscription API ──

    def subscribe(
        self, substrate: str, callback: Callable[[str, str], object]
    ) -> int:
        """v1.9.0 (CIRISPersist#84) — register a change-feed callback.

        ``callback`` is invoked as ``callback(substrate, event_json)``
        each time a producer calls :meth:`publish_change` for
        ``substrate``. ``substrate`` must be a known substrate family
        (``cirislens``, ``cirislens_secrets``, ``cirislens_derived``,
        ``cirisgraph``, ``cirisnode``) — an unknown name raises
        ``ValueError``. Returns an opaque subscription id for
        :meth:`unsubscribe`.
        """

    def unsubscribe(self, subscription_id: int) -> bool:
        """v1.9.0 (CIRISPersist#84) — remove a change-feed callback by
        the id :meth:`subscribe` returned. ``True`` if it was
        registered. Idempotent."""

    def publish_change(self, substrate: str, event_json: str) -> int:
        """v1.9.0 (CIRISPersist#84) — publish a change event to every
        callback subscribed to ``substrate``; returns the number of
        callbacks invoked.

        ``event_json`` is an opaque JSON string (the wire shape is a
        producer/subscriber contract; persist does not parse it).
        Dispatch is synchronous and in-process: every matching
        callback runs, in subscription-id order, before this returns.
        A callback that raises is caught and logged — the exception
        does not propagate here and does not stop the other
        callbacks. No persistence/replay: a subscriber attaching after
        a publish does not see that event.
        """

    def list_subscriptions(self) -> str:
        """v1.9.0 (CIRISPersist#84) — JSON snapshot of the change-feed
        subscription registry: ``{"<id>": "<substrate>", ...}``."""

    @property
    def subscription_count(self) -> int:
        """v1.9.0 (CIRISPersist#84) — number of live change-feed
        subscriptions."""

    def register_public_key(
        self,
        signature_key_id: str,
        public_key_b64: str,
        agent_id_hash: str | None = None,
    ) -> None:
        """Register a raw Ed25519 verifying key in the **lens audit-chain
        directory** (`accord_public_keys`).

        Used by lens-tier verifiers to look up the signing key for an
        audit-chain entry. Distinct from `register_federation_key` /
        `put_public_key`, which write to the **federation directory**
        (`federation_keys` with full signed envelope + V020 trust
        columns + V021 trust grants).

        Idempotent on the same key/value; rejects rotation (registering
        a different key for an existing key id raises).
        """

    def audit_canonicalize_for_hash(self, entry_json: str) -> bytes:
        """v1.5.4 — Return the exact canonical bytes whose SHA-256 equals
        the audit entry's `entry_hash`.

        Workflow:
        1. Build AuditEntry JSON with `entry_hash = ""` and `signature = ""`.
        2. `ch = engine.audit_canonicalize_for_hash(json.dumps(entry))`
        3. `entry["entry_hash"] = base64(sha256(ch).digest())`

        Rule mirrors `crate::audit::verify::compute_entry_hash`: both
        `entry_hash` and `signature` are zeroed pre-canonicalization;
        canonicalization is PythonJsonDumpsCanonicalizer (sorted keys,
        no whitespace, ensure_ascii=True). Companion of
        `audit_canonicalize_for_signing`.
        """

    def audit_canonicalize_for_signing(self, entry_json: str) -> bytes:
        """v1.5.4 — Return the exact canonical bytes the audit entry's
        Ed25519 `signature` covers.

        Workflow:
        4. `cs = engine.audit_canonicalize_for_signing(json.dumps(entry))`
        5. `entry["signature"] = base64(your_signer.sign_ed25519(cs))`
        6. `engine.audit_record_entry(json.dumps(entry))`

        Rule: only `signature` is stripped — `entry_hash` participates
        in the signed body so a chain rewrite that flips a subsequent
        entry's `prev_hash` invalidates this entry's signature too.
        """

    def register_federation_key(
        self,
        identity_type: str,
        identity_ref: str,
        valid_until: str | None = None,
        registration_envelope_json: str | None = None,
        roles: list[str] | None = None,
    ) -> str:
        """v1.5.3 — One-call helper that registers THIS engine's local
        pubkey in the **federation directory** (`federation_keys`).

        Composes the existing canonicalize + sign + put_public_key
        primitives so callers don't re-implement persist's canonical-bytes
        rule in Python. Returns the registered `key_id` (equals
        `engine.local_key_id()`).

        Internally:
        1. Canonicalizes `registration_envelope_json` (defaults to `{}`)
           via persist's `PythonJsonDumpsCanonicalizer`.
        2. Signs canonical bytes with the engine's local Ed25519 key.
        3. Builds a self-signed `SignedKeyRecord` (scrub_key_id =
           local_key_id).
        4. Calls `put_public_key` — backend dispatch + cold-path
           ML-DSA-65 PQC attach handled automatically.

        Raises:
            ValueError: no local signing identity, malformed valid_until,
                or unparseable registration_envelope_json.
            RuntimeError: backend / IO error.
        """

    def receive_and_persist(self, body: bytes) -> BatchSummary:
        """Run the FSD §3.3 ingest pipeline on a batch body.

        Raises:
            ValueError: schema / verify / scrub rejection — caller
                surfaces as HTTP 4xx.
            RuntimeError: backend / IO error — caller surfaces as HTTP
                5xx.
        """

    # ── v1.5.0 Phase H: trust-grant + Merkle transparency surface ────
    #
    # 8 methods wrapping the federation::emit + federation::read APIs.
    # Return shapes are JSON strings (caller parses); typed Python
    # classes are reserved for the Phase J release cut.

    def grant_trust(
        self,
        tenant_id: str,
        grantee_key: str,
        purpose: str,
        scope: str,
        expires_at: str | None,
        rationale: str,
    ) -> str:
        """Emit a signed TrustGrant audit-chain entry (FSD §4.1).

        ``purpose`` must be one of ``"technical" | "deferral" |
        "contribution" | "service"``. ``expires_at`` is ISO-8601 or
        ``None``. Requires a steward key configured on the Engine
        (``local_key_id`` + ``local_key_path``).

        Returns a JSON-encoded ``TrustGrantReceipt`` string with
        ``{ grant_id, chain_event_id, chain_event_hash, tenant_id,
        tree_size_at_emit, sth }``.

        Raises:
            ValueError: malformed purpose / expires_at, self-grant,
                or no steward signer configured.
            RuntimeError: signing or backend failure.
        """

    def revoke_trust_grant(
        self,
        tenant_id: str,
        grantee_key: str,
        purpose: str,
        scope: str,
    ) -> str:
        """Revoke a trust grant per FSD §3.4 (re-issuance with
        ``expires_at = now()``, rationale = ``"revocation"``). Returns
        a JSON-encoded ``TrustGrantReceipt`` for the revocation event."""

    def lookup_trust_grant(
        self,
        grantee_key: str,
        purpose: str,
        scope: str,
    ) -> str:
        """Look up live (non-revoked, non-expired) trust grants for
        ``(grantee_key, purpose, scope)``. Returns a JSON-array string
        of ``TrustGrantRow`` objects. Wildcard scope grants (``"*"``)
        surface alongside exact matches per FSD §3.3."""

    def list_trust_grants(self, filter_json: str) -> str:
        """Filter query over ``federation_trust_grants``. ``filter_json``
        deserializes into ``TrustGrantFilter``. Returns a JSON-array
        string of ``TrustGrantRow`` objects."""

    def get_trust_grant(self, grant_id: str) -> str | None:
        """Point lookup by canonical UUID ``grant_id``. Returns a
        JSON-encoded ``TrustGrantRow`` or ``None``."""

    def current_sth(self, tenant_id: str) -> str | None:
        """Fetch the current ``SignedTreeHead`` for the per-tenant
        Merkle log. Returns a JSON-encoded ``SignedTreeHead`` or
        ``None``."""

    def trust_grant_inclusion_proof(self, grant_id: str) -> str:
        """Generate the full inclusion-proof bundle for a trust grant.
        Returns a JSON object with ``{ sth, merkle_proof,
        leaf_canonical_bytes (base64) }``.

        Raises:
            KeyError: grant_id has no projection row, the tenant has
                no STH, or the merkle leaf is missing.
        """

    # ── v1.5.9 (CIRISPersist#59 #1) — agent tasks substrate ──────────

    def task_upsert(self, task_json: str) -> str:
        """v1.5.9 — Idempotent upsert keyed on ``task_id``.

        ``task_json`` is a JSON-encoded ``Task`` shape (see the
        ``ciris_persist.tasks`` module). Re-insert with the same
        payload is a no-op; re-insert with differing payload
        overwrites the mutable columns and preserves ``created_at``.

        Returns the JSON-encoded ``TaskUpsertOutcome`` envelope
        ``{"outcome": "stored" | "already_exists", "task": <Task>}``
        (v1.5.22, CIRISPersist#61). ``stored`` carries the
        canonical post-upsert row (caller's ``task_id`` wins).
        ``already_exists`` carries the EXISTING row when the V036
        unique index on ``(agent_occurrence_id,
        context_json->>'correlation_id')`` would have been violated
        by a fresh ``task_id`` — caller reconciles to the canonical
        ``task_id``. The ``already_exists`` outcome only fires when
        ``context.correlation_id`` is set; rows without one insert
        normally as ``stored``.

        **Breaking change in v1.5.22:** prior versions returned
        ``None``. Callers that ignored the return value continue to
        work; callers that want dedup-detection use the new envelope.
        """

    def task_get(self, task_id: str) -> str | None:
        """v1.5.9 — Read one task by id. Returns the JSON-encoded
        ``Task`` row or ``None`` if no matching row exists.
        """

    def task_list(
        self,
        filter_json: str,
        cursor_json: str | None,
        limit: int,
    ) -> str:
        """v1.5.9 — Cursor-paged task listing. Returns the JSON-encoded
        ``TaskListPage`` ({"items": [...], "next_cursor": {...}|None}).

        ``filter_json`` accepts (all optional): ``agent_occurrence_id``,
        ``status``, ``channel_id``, ``parent_task_id``,
        ``updated_after``, ``updated_before``, and as of v1.5.21
        (CIRISPersist#62) ``created_before`` / ``created_after``
        (RFC 3339 timestamps; emitted as SQL ``created_at < ?`` /
        ``created_at >= ?`` predicates so callers don't paginate
        whole occurrences and filter in Python).
        """

    def task_update_status(
        self,
        task_id: str,
        new_status: str,
        outcome_json: str | None,
    ) -> bool:
        """v1.5.9 — Focused status update + optional outcome merge.

        ``new_status`` is one of ``pending`` / ``active`` /
        ``completed`` / ``failed`` / ``cancelled`` / ``deferred``.
        ``outcome_json`` (when not None) is decoded and stored into the
        ``outcome_json`` column; ``None`` preserves the existing value.

        Returns ``True`` when a row was updated, ``False`` when no
        matching task exists (no error — caller treats as stale id).
        """

    def task_try_claim_shared(self, task_json: str) -> str:
        """v1.5.9 — Atomic INSERT-OR-IGNORE claim keyed on ``task_id``.

        Returns the JSON wire-shape
        ``{"outcome": "stored" | "already_claimed", "task": <Task>}``.
        First caller wins with ``"stored"``; subsequent callers get
        ``"already_claimed"`` carrying the EXISTING row (not the
        caller's payload).
        """

    def task_delete(self, task_id: str) -> bool:
        """v1.5.9 — Delete a task by id.

        Returns ``True`` if a row was deleted, ``False`` on
        missing/already-deleted (idempotent). FK-protected: children
        pointing at this row reject the delete as Conflict.
        """

    # ── v1.5.10 (CIRISPersist#59 #2) — agent thoughts substrate ─────

    def thought_upsert(self, thought_json: str) -> None:
        """v1.5.10 — Idempotent upsert keyed on ``thought_id``.

        ``thought_json`` is a JSON-encoded ``Thought`` shape (see the
        ``ciris_persist.thoughts`` module). Re-insert with the same
        payload is a no-op; re-insert with differing payload
        overwrites the mutable columns and preserves ``created_at``.
        """

    def thought_get(self, thought_id: str) -> str | None:
        """v1.5.10 — Read one thought by id. Returns the JSON-encoded
        ``Thought`` row or ``None`` if no matching row exists.
        """

    def thought_list(
        self,
        filter_json: str,
        cursor_json: str | None,
        limit: int,
    ) -> str:
        """v1.5.10 — Cursor-paged thought listing. Returns the
        JSON-encoded ``ThoughtListPage``
        ({"items": [...], "next_cursor": {...}|None}).

        ``filter_json`` accepts (all optional): ``source_task_id``,
        ``status``, ``agent_occurrence_id``, ``parent_thought_id``,
        ``updated_after``, ``updated_before``, and as of v1.5.21
        (CIRISPersist#62) ``created_before`` / ``created_after``
        (RFC 3339 timestamps; SQL ``created_at`` range predicate
        emitted server-side).
        """

    def thought_update_status(
        self,
        thought_id: str,
        new_status: str,
        final_action_json: str | None,
    ) -> bool:
        """v1.5.10 — Focused status update + optional final_action
        merge.

        ``new_status`` is one of ``pending`` / ``processing`` /
        ``completed`` / ``failed`` / ``deferred``.
        ``final_action_json`` (when not None) is decoded and stored
        into the ``final_action_json`` column; ``None`` preserves the
        existing value.

        Returns ``True`` when a row was updated, ``False`` when no
        matching thought exists (no error — caller treats as stale
        id).
        """

    def thought_get_descendants(self, thought_id: str) -> str:
        """v1.5.10 — Walk the ``parent_thought_id`` chain rooted at
        ``thought_id``.

        Returns the JSON-encoded ``list[Thought]`` (root + transitive
        descendants) ordered by ``(thought_depth ASC, thought_id ASC)``.
        Empty list when the root has no matching row (not an error).
        Uses a recursive CTE on both backends.
        """

    def thought_delete(self, thought_id: str) -> bool:
        """v1.5.20 (CIRISPersist#60) — Delete a thought by id.

        Returns ``True`` if a row was deleted, ``False`` on missing or
        already-deleted (idempotent). The self-FK on
        ``parent_thought_id`` rejects the delete with ``Conflict`` if
        children exist — caller deletes leaves-first or walks
        :meth:`thought_get_descendants` first. The cascade on
        ``source_task_id`` (V035) is the inverse direction:
        :meth:`task_delete` of a parent task automatically cascades
        its thoughts.
        """

    # ── v1.5.11 (CIRISPersist#59 #3) — service correlations substrate

    def correlation_record(self, correlation_json: str) -> None:
        """v1.5.11 — Record a correlation. INSERT-OR-IGNORE keyed on
        ``correlation_id``.

        ``correlation_json`` is a JSON-encoded ``Correlation`` shape
        (see the ``ciris_persist.correlations`` module). First writer
        wins; a re-record with the same ``correlation_id`` is a
        silent no-op (idempotent retry). State advancement is the
        caller's responsibility — use ``correlation_update_status``
        to advance an in-flight row.
        """

    def correlation_get(self, correlation_id: str) -> str | None:
        """v1.5.11 — Read one correlation by id. Returns the JSON-
        encoded ``Correlation`` row or ``None`` when no matching row.
        """

    def correlation_update_status(
        self,
        correlation_id: str,
        new_status: str,
        response_data_json: str | None,
    ) -> bool:
        """v1.5.11 — Focused status update + optional response_data
        merge.

        ``new_status`` is one of ``pending`` / ``active`` /
        ``completed`` / ``failed`` / ``cancelled``.
        ``response_data_json`` (when not None) is decoded and stored
        into the ``response_data`` column; ``None`` preserves the
        existing value.

        Returns ``True`` when a row was updated, ``False`` when no
        matching correlation exists (no error — caller treats as
        stale id).
        """

    def correlation_query(
        self,
        filter_json: str,
        cursor_json: str | None,
        limit: int,
    ) -> str:
        """v1.5.11 — Cursor-paged query. Returns JSON-encoded
        ``CorrelationListPage`` (``{"items": [...], "next_cursor":
        {...}|None}``). The filter shape mirrors
        ``CorrelationFilter`` — supported fields:
        ``service_type``, ``correlation_type``, ``trace_id``,
        ``metric_name``, ``retention_policy``,
        ``agent_occurrence_id``, ``timestamp_after`` /
        ``timestamp_before`` (event-time window),
        ``updated_after`` / ``updated_before`` (row-update window).
        Cursor pagination on ``(updated_at, correlation_id)``.
        """

    # ── v1.5.12 (CIRISPersist#59 #4) — scheduled tasks substrate

    def scheduled_task_upsert(self, task_json: str) -> None:
        """v1.5.12 — Upsert a scheduled task. ``task_json`` is a
        JSON-encoded ``ScheduledTask`` (see the
        ``ciris_persist.scheduled_tasks`` module). INSERT on first
        call, UPDATE on conflict by ``id``. All columns except
        ``created_at`` overwrite on conflict; ``created_at`` is
        preserved.

        Note: the ``status`` field on the wire is lowercase
        snake_case (``"pending"`` / ``"active"`` / ``"complete"`` /
        ``"failed"``) while the SQL CHECK vocabulary is UPPERCASE
        — Rust handles the translation. ``origin_thought_id`` must
        reference an existing row in ``cirislens.thoughts`` (PG:
        DEFERRABLE FK; SQLite: immediate FK).
        """

    def scheduled_task_list_due(
        self,
        agent_occurrence_id: str,
        now_iso: str,
        limit: int,
    ) -> str:
        """v1.5.12 — Scheduler tick query. Returns JSON-encoded
        ``list[ScheduledTask]`` of tasks where
        ``next_trigger_at <= now`` AND status is ``PENDING`` or
        ``ACTIVE``, scoped to the given occurrence. Ordered ASC by
        ``next_trigger_at`` for fair scheduling. ``now_iso`` is
        RFC 3339; ``limit`` is the batch size (typical 100). Hits
        the ``scheduled_tasks_due`` partial index.
        """

    def scheduled_task_update_after_trigger(
        self,
        task_id: str,
        last_triggered_at_iso: str,
        next_trigger_at_iso: str | None,
        deferral_count: int,
        deferral_history_json: str | None = None,
        new_status: str | None = None,
    ) -> bool:
        """v1.5.12 — Post-fire bookkeeping. Updates
        ``last_triggered_at`` + ``next_trigger_at`` (None → NULL) +
        ``deferral_count``. Optional ``deferral_history_json``
        (None → preserve existing). Optional ``new_status`` advances
        the lifecycle (None → preserve existing); accepts lowercase
        snake_case wire format (``pending`` / ``active`` /
        ``complete`` / ``failed``).

        Returns ``True`` when a row was updated, ``False`` when no
        matching task exists (no error — caller treats as stale id).
        """

    # ── v1.5.13 (CIRISPersist#59 #5) — tickets substrate

    def ticket_upsert(self, ticket_json: str) -> None:
        """v1.5.13 — Upsert a ticket. ``ticket_json`` is a
        JSON-encoded ``Ticket`` (see the ``ciris_persist.tickets``
        module). INSERT on first call, UPDATE on conflict by
        ``ticket_id``. All columns except ``created_at`` and
        ``submitted_at`` overwrite on conflict; both creation-time
        columns are preserved.

        Note: the ``status`` field on the wire is lowercase
        snake_case 8-value (``"pending"`` / ``"assigned"`` /
        ``"in_progress"`` / ``"blocked"`` / ``"deferred"`` /
        ``"completed"`` / ``"cancelled"`` / ``"failed"``) — matches
        the SQL CHECK vocabulary directly. ``priority`` is 1-10
        (default 5). ``agent_occurrence_id`` default is
        ``"__shared__"`` (cross-occurrence work items).
        """

    def ticket_get(self, ticket_id: str) -> str | None:
        """v1.5.13 — Point lookup. Returns JSON-encoded ``Ticket`` or
        ``None`` when no matching row."""

    def ticket_list(
        self,
        filter_json: str,
        cursor_json: str | None,
        limit: int,
    ) -> str:
        """v1.5.13 — Cursor-paged query. Returns JSON-encoded
        ``TicketListPage`` (``{"items": [...], "next_cursor":
        {...}|None}``). The filter shape mirrors ``TicketFilter`` —
        supported fields: ``sop``, ``ticket_type``, ``status``,
        ``email``, ``agent_occurrence_id``, ``automated``,
        ``deadline_before`` (due-deadline scan; only tickets with a
        non-NULL deadline at or before this timestamp),
        ``last_updated_after`` / ``last_updated_before``
        (row-update window). Cursor pagination on
        ``(last_updated, ticket_id)``, newest-first.
        """

    def ticket_assign(
        self,
        ticket_id: str,
        user_identifier: str,
        new_status: str | None = None,
    ) -> bool:
        """v1.5.13 — Atomic assignment + status flip. Sets
        ``user_identifier`` to the supplied value, advances
        ``status`` (default ``assigned``, or caller-supplied via
        ``new_status`` — lowercase snake_case wire format), bumps
        ``last_updated`` to NOW. Idempotent on ``(ticket_id,
        user_identifier)``: re-assigning the same ticket to the same
        user is a no-op (returns True; the row is already in the
        assigned state). Returns ``False`` when no matching ticket.
        """

    def ticket_update_status(
        self,
        ticket_id: str,
        new_status: str,
        completed_at_iso: str | None = None,
        notes: str | None = None,
    ) -> bool:
        """v1.5.13 — Focused status update. ``new_status`` is the
        lowercase snake_case wire format. Optional
        ``completed_at_iso`` (RFC 3339) — on terminal-state
        transitions (``completed`` / ``cancelled`` / ``failed``)
        the caller supplies the timestamp; the trait doesn't enforce.
        Optional ``notes`` overwrites the existing value when
        supplied (``None`` preserves the existing value). Bumps
        ``last_updated`` to NOW.

        Returns ``True`` when a row was updated, ``False`` when no
        matching ticket (no error — callers treat as stale id).
        """

    # ── v1.5.14 (CIRISPersist#59 #6) — deferral_reports substrate

    def deferral_record(self, report_json: str) -> str:
        """v1.5.14 — Record a deferral report. ``report_json`` is a
        JSON-encoded ``DeferralReport`` (see the
        ``ciris_persist.deferral_reports`` module).

        Returns a JSON-encoded ClaimResult wire shape:
        ``{"outcome": "stored" | "already_claimed",
        "report": <DeferralReport>}``. The race winner sees
        ``"stored"`` and their own row; race losers see
        ``"already_claimed"`` and the EXISTING row.

        FK semantics: ``task_id`` must reference an existing row in
        ``cirislens.tasks``, and ``thought_id`` must reference an
        existing row in ``cirislens.thoughts``. PG: both FKs are
        DEFERRABLE INITIALLY DEFERRED so a single tx can write
        ``(task, thought, deferral_report)`` in order. SQLite: FKs
        are immediate; callers ensure parent rows exist before
        recording.
        """

    def deferral_get(self, message_id: str) -> str | None:
        """v1.5.14 — Point lookup. Returns JSON-encoded
        ``DeferralReport`` or ``None`` when no matching row."""

    def deferral_list_active(self, filter_json: str, limit: int) -> str:
        """v1.5.14 — WA queue: list deferrals awaiting resolution
        (``resolved_at IS NULL``), newest-first by ``created_at``.
        ``filter_json`` is a JSON-encoded ``DeferralFilter`` —
        supported fields: ``task_id``, ``thought_id``,
        ``created_after``, ``created_before`` (RFC 3339 timestamps).
        Returns JSON-encoded ``list[DeferralReport]``. Hits the
        partial index ``deferral_reports_active``.
        """

    def deferral_resolve(
        self,
        message_id: str,
        resolved_at: str,
        resolution_notes: str | None = None,
    ) -> bool:
        """v1.5.14 — Mark a deferral as resolved. Sets
        ``resolved_at`` (RFC 3339 ISO string) and
        ``resolution_notes`` (overwrites; ``None`` clears).

        Returns ``True`` when a row was updated, ``False`` when no
        matching row (no error — callers treat as stale id).
        """

    # ── v1.5.15 (CIRISPersist#59 #7) — maintenance_locks substrate

    def lock_try_acquire(
        self,
        lock_key: str,
        locked_by: str,
        timeout_seconds: int,
        metadata_json: str | None = None,
    ) -> str | None:
        """v1.5.15 — Atomic try-acquire of a named lock. Returns the
        JSON-encoded ``MaintenanceLock`` (race winner — clean
        acquire or steal-the-stale of an expired holder) or
        ``None`` (contention — held by another active caller; the
        caller should treat ``None`` as "try again later", NOT as
        an exception).

        Race-safe: implemented as a single-statement UPSERT with a
        WHERE clause that gates on
        ``locked_by IS NULL OR locked_by = caller OR locked_at +
        timeout < server_now``. PG uses ``NOW()`` server-side;
        SQLite uses ``julianday('now')`` server-side. Both stamp
        ``locked_at`` against the same server clock so the
        steal-vs-active decision is consistent.

        Same-holder re-acquire succeeds and refreshes
        ``lock_timeout_seconds`` + ``locked_at`` + ``metadata`` to
        the new caller-supplied values.

        ``metadata_json`` is an optional JSON-encoded payload (any
        valid JSON value: object, array, scalar). Stored verbatim
        in the row's ``metadata`` column for operator
        observability.
        """

    def lock_release(self, lock_key: str, locked_by: str) -> bool:
        """v1.5.15 — Release a lock IFF the caller still holds it.
        Returns ``True`` when the lock was cleared; ``False`` when
        the row doesn't exist or the row's ``locked_by`` doesn't
        match the supplied ``locked_by`` (no-op — caller treats
        ``False`` as "not yours to release").
        """

    def lock_get(self, lock_key: str) -> str | None:
        """v1.5.15 — Read current lock state. Returns the
        JSON-encoded ``MaintenanceLock`` or ``None`` when no row
        for ``lock_key`` exists. ``locked_by IS NULL`` AND
        ``locked_at IS NULL`` means the row exists but no caller
        currently holds the lock; callers also check ``locked_at
        + lock_timeout_seconds`` against wall-clock to decide if a
        present-but-expired holder is stealable.
        """

    # ── v1.5.16 (CIRISPersist#59 #8) — creation_ceremonies substrate

    def ceremony_record(self, ceremony_json: str) -> str:
        """v1.5.16 — Record a creation ceremony. ``ceremony_json``
        is a JSON-encoded ``CreationCeremony`` (see the
        ``ciris_persist.creation_ceremonies`` module). INSERT ON
        CONFLICT (ceremony_id) DO NOTHING — write-once shape.

        Returns a JSON-encoded ClaimResult object:
        ``{"outcome": "stored" | "already_claimed",
          "ceremony": <CreationCeremony>}``.
        The race winner sees ``"stored"`` and their own row; race
        losers see ``"already_claimed"`` and the EXISTING row
        (the loser's payload is discarded — write-once contract).
        """

    def ceremony_get(self, ceremony_id: str) -> str | None:
        """v1.5.16 — Point lookup. Returns JSON-encoded
        ``CreationCeremony`` or ``None`` when no matching row."""

    def ceremony_list(self, filter_json: str, limit: int) -> str:
        """v1.5.16 — History query. ``filter_json`` is a
        JSON-encoded ``CeremonyFilter`` — supported fields:
        ``creator_agent_id``, ``creator_human_id``,
        ``wise_authority_id``, ``new_agent_id``,
        ``ceremony_status`` (lowercase snake_case),
        ``timestamp_after``, ``timestamp_before`` (RFC 3339
        timestamps).

        Returns JSON-encoded ``list[CreationCeremony]`` ordered by
        ``(timestamp, ceremony_id)``, newest-first, limited.
        """

    def ceremony_update_status(
        self,
        ceremony_id: str,
        new_status: str,
    ) -> bool:
        """v1.5.16 — Atomic ceremony-status advance. ``new_status``
        is a lowercase snake_case string from the 5-value
        vocabulary (``pending`` | ``in_progress`` | ``completed`` |
        ``failed`` | ``revoked``).

        Returns ``True`` when a row was updated, ``False`` when no
        matching row (no error — callers treat as stale id).
        """

    # ── v1.5.17 (CIRISPersist#59 #9) — continuity_awareness substrate

    def continuity_record(self, record_json: str) -> str:
        """v1.5.17 — Record a shutdown event. ``record_json`` is a
        JSON-encoded ``ContinuityAwareness`` (see the
        ``ciris_persist.continuity_awareness`` module). INSERT ON
        CONFLICT (id) DO NOTHING — write-once shape.

        First substrate with a cross-substrate FK: the
        ``(preservation_node_id, preservation_scope)`` pair MUST
        reference an existing cirisgraph node row. A missing parent
        surfaces as ``Conflict``.

        Returns a JSON-encoded ClaimResult object:
        ``{"outcome": "stored" | "already_claimed",
          "record": <ContinuityAwareness>}``.
        The race winner sees ``"stored"`` and their own row; race
        losers see ``"already_claimed"`` and the EXISTING row.
        """

    def continuity_get_latest(self, agent_id: str) -> str | None:
        """v1.5.17 — Get the most recent shutdown for an agent —
        used on next boot to surface "where did I leave off."
        Returns JSON-encoded ``ContinuityAwareness`` or ``None``
        when the agent has no recorded shutdowns. Ordered by
        ``shutdown_timestamp DESC``, ``LIMIT 1``.
        """

    def continuity_record_reactivation(self, agent_id: str) -> bool:
        """v1.5.17 — Increment ``reactivation_count`` on the
        most-recent non-terminal shutdown for ``agent_id``. Used
        when the agent successfully resumes from a non-terminal
        shutdown.

        Returns ``True`` when a row was updated, ``False`` when the
        agent has only terminal shutdowns or no shutdowns at all
        (callers treat as "nothing to reactivate" — not an error).
        """

    # ── v1.5.18 (CIRISPersist#59 #10) — feedback_mappings substrate

    def feedback_record(self, feedback_json: str) -> str:
        """v1.5.18 — Record a feedback row. ``feedback_json`` is a
        JSON-encoded ``FeedbackMapping`` with 5 fields:
        ``feedback_id`` (PK, required), ``source_message_id``
        (optional wire-message id), ``target_thought_id`` (optional
        FK to ``cirislens.thoughts``), ``feedback_type`` (free-form
        string — agent uses ``approval`` / ``correction`` /
        ``clarification``), ``created_at`` (RFC 3339 timestamp).
        INSERT ON CONFLICT (feedback_id) DO NOTHING — write-once
        shape.

        FK semantics: when ``target_thought_id`` is non-NULL the
        referenced thought MUST exist or the call returns
        ``Conflict``. NULL ``target_thought_id`` bypasses the FK on
        both backends.

        Returns a JSON-encoded ClaimResult object:
        ``{"outcome": "stored" | "already_claimed",
          "feedback": <FeedbackMapping>}``.
        The race winner sees ``"stored"`` and their own row; race
        losers see ``"already_claimed"`` and the EXISTING row.
        """

    def feedback_list_for_thought(self, thought_id: str, limit: int) -> str:
        """v1.5.18 — List feedback rows attached to a specific
        thought. Ordered ``created_at DESC, feedback_id DESC``.
        Returns JSON-encoded ``list[FeedbackMapping]``. Hits the
        partial index ``feedback_mappings_thought``.
        """

    def feedback_list(self, filter_json: str, limit: int) -> str:
        """v1.5.18 — Filter-query feedback rows. ``filter_json`` is a
        JSON-encoded ``FeedbackFilter`` — supported fields:
        ``source_message_id``, ``feedback_type``, ``created_after``,
        ``created_before`` (RFC 3339 timestamps for the time
        window). Returns JSON-encoded ``list[FeedbackMapping]``,
        ordered DESC by ``created_at``.
        """

    # ── v1.5.19 (CIRISPersist#59 #11, FINAL) — wa_cert substrate

    def wa_cert_upsert(self, cert_json: str) -> None:
        """v1.5.19 — Idempotent upsert of a WA cert. ``cert_json`` is
        a JSON-encoded ``WaCert`` with 24 fields: ``wa_id`` (PK,
        required), ``name`` (required), ``role`` (required;
        ``root`` | ``authority`` | ``observer``), ``pubkey``
        (required), ``jwt_kid`` (required, UNIQUE across the
        directory), ``password_hash``, ``api_key_hash``,
        ``oauth_provider``, ``oauth_external_id``, ``oauth_links``
        (JSON object), ``veilid_id``, ``auto_minted`` (bool,
        default False), ``parent_wa_id`` (self-FK; nullable),
        ``parent_signature``, ``scopes`` (JSON array, required),
        ``custom_permissions`` (JSON object), ``adapter_id``,
        ``adapter_name``, ``adapter_metadata`` (JSON object),
        ``token_type`` (``standard`` | ``session`` | ``api_key`` |
        ``oauth`` | ``service``; default ``standard``), ``created``
        (RFC 3339, required, PRESERVED across upserts),
        ``last_login`` (RFC 3339, nullable), ``active`` (bool,
        default True).

        UPSERT on ``wa_id`` — every column except ``wa_id`` +
        ``created`` overwrites on conflict. Duplicate ``jwt_kid``
        across different ``wa_id``s raises ``Conflict``; non-NULL
        ``parent_wa_id`` referencing a missing parent raises
        ``Conflict``.
        """

    def wa_cert_get(self, wa_id: str) -> str | None:
        """v1.5.19 — Point lookup by ``wa_id``. Returns JSON-encoded
        ``WaCert`` or ``None`` when no row matches.
        """

    def wa_cert_get_by_kid(self, jwt_kid: str) -> str | None:
        """v1.5.19 — JWT verification hot path. Lookup by
        ``jwt_kid`` via the unique ``wa_cert_jwt_kid`` index.
        Returns JSON-encoded ``WaCert`` or ``None``.
        """

    def wa_cert_get_by_oauth(
        self, oauth_provider: str, oauth_external_id: str
    ) -> str | None:
        """v1.5.19 — OAuth login path. Lookup by
        ``(oauth_provider, oauth_external_id)`` via the partial
        ``wa_cert_oauth`` index. Returns JSON-encoded ``WaCert`` or
        ``None``.
        """

    def wa_cert_list_by_role(self, role: str, limit: int) -> str:
        """v1.5.19 — Role-based listing. ``role`` is the lowercase
        SQL string (``root`` | ``authority`` | ``observer``).
        Returns JSON-encoded ``list[WaCert]`` of certs with
        ``active = True`` filtered by role. Ordered
        ``created DESC, wa_id DESC``. Hits the partial
        ``wa_cert_role_active`` index.
        """

    def wa_cert_set_active(self, wa_id: str, active: bool) -> bool:
        """v1.5.19 — Activity toggle. Sets ``active`` to the
        supplied value. Returns ``True`` if the row exists
        (idempotent for same-value toggles); ``False`` if ``wa_id``
        doesn't exist.
        """

    def wa_cert_update_last_login(
        self, wa_id: str, login_time_iso: str
    ) -> bool:
        """v1.5.19 — Last-login bookkeeping. ``login_time_iso`` is
        an RFC 3339 timestamp string. Returns ``True`` if the row
        was updated; ``False`` if ``wa_id`` doesn't exist.
        """

    # ── v1.5.23 (CIRISPersist#64) — service-token revocation substrate

    def service_token_revocation_record(self, revocation_json: str) -> None:
        """v1.5.23 (CIRISPersist#64) — Record a service-token revocation.

        Idempotent on ``token_hash`` (PK; ON CONFLICT DO NOTHING).
        First record wins. ``revocation_json`` is a JSON-encoded
        ``RevokedServiceToken`` shape:
        ``{"token_hash": "...", "revoked_at": "<rfc3339>", "revoked_by": "...", "reason": "..."}``.
        All four fields required (non-empty).

        Replaces CIRISAgent's standalone ``revoked_service_tokens.db``
        aiosqlite file — last aiosqlite consumer in the agent.
        """

    def service_token_revocation_list(self) -> str:
        """v1.5.23 (CIRISPersist#64) — List ALL revoked tokens.

        Returns the JSON-encoded ``list[RevokedServiceToken]``.
        Agent caches in memory on startup; this method runs once at
        boot. Order unspecified (caller indexes by token_hash).
        """

    def service_token_revocation_check(self, token_hash: str) -> str | None:
        """v1.5.23 (CIRISPersist#64) — Point-lookup check.

        Returns the JSON-encoded ``RevokedServiceToken`` row if
        revoked, ``None`` otherwise. Backed by the PRIMARY KEY index.
        """

    # ── v1.7.1 (CIRISPersist#83) — identity-sequence substrate ──────

    def next_sequence(self, identity: str, stream: str) -> int:
        """v1.7.1 (CIRISPersist#83) — Atomically bump and return the
        next monotonic value for ``(identity, stream)``.

        First call for a pair returns 1, then 2, 3, … Durable,
        monotonic, and correct under concurrent callers.

        A CIRIS 3.0 runtime holds exactly one Ed25519 identity, and
        every in-process consumer (agent, NodeCore, LensCore) plus
        every agent occurrence signs with that one key. Anything
        emitting *ordered* signed output (e.g. NodeCore
        network-message sequence numbers) needs a counter atomic
        across all of those signers — otherwise two occurrences both
        emit seq N and the signed stream forks. This is that
        counter. The bump is a single atomic
        ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING``.

        ``identity`` and ``stream`` must both be non-empty. The
        ``stream`` namespaces independent counters under one
        identity (e.g. one stream per signed output kind).
        """

    def peek_sequence(self, identity: str, stream: str) -> int:
        """v1.7.1 (CIRISPersist#83) — Read the last-issued value for
        ``(identity, stream)`` WITHOUT bumping it.

        Returns ``0`` if the pair has never been issued. ``identity``
        and ``stream`` must both be non-empty.
        """

    # ── v1.7.3 (CIRISPersist#81) — occurrence registry ──────────────

    def register_occurrence(
        self,
        occurrence_id: str,
        identity: str,
        ttl_seconds: int,
        metadata_json: str | None = None,
    ) -> None:
        """v1.7.3 (CIRISPersist#81) — Register (or re-register) a live
        occurrence with a liveness TTL.

        Idempotent on ``occurrence_id``: re-registering refreshes
        ``registered_at``, ``last_heartbeat``, and ``expires_at``.
        ``ttl_seconds`` must be > 0; ``expires_at = now + ttl_seconds``.
        A crashed occurrence ages out past ``expires_at`` without a
        clean deregister — TTL-based liveness, not membership.

        Under the one-key model (PoB §3.2) every occurrence of an
        agent signs with the *same* Ed25519 ``identity``, so this
        registry is endpoint liveness under a stable identity, not a
        membership change. ``metadata_json``, if provided, must be a
        JSON value (e.g. endpoint addresses, version).

        ``occurrence_id`` and ``identity`` must both be non-empty.
        """

    def heartbeat_occurrence(self, occurrence_id: str, ttl_seconds: int) -> bool:
        """v1.7.3 (CIRISPersist#81) — Bump ``last_heartbeat`` and
        ``expires_at`` for an already-registered occurrence.

        Returns ``False`` if ``occurrence_id`` is not in the registry
        — a heartbeat for an unknown occurrence is a no-op, not an
        error; the caller should ``register_occurrence`` first.
        ``ttl_seconds`` must be > 0.
        """

    def deregister_occurrence(self, occurrence_id: str) -> bool:
        """v1.7.3 (CIRISPersist#81) — Clean shutdown: remove the
        occurrence row immediately, without waiting for TTL expiry.

        Returns ``True`` if a row was removed, ``False`` if it wasn't
        registered. Idempotent. This is what distinguishes a clean
        shutdown from a crash (which ages out via TTL instead).
        """

    def list_live_occurrences(self, identity: str) -> str:
        """v1.7.3 (CIRISPersist#81) — List currently-live occurrences
        for ``identity`` — rows whose ``expires_at > now``.

        Returns a JSON-encoded array of ``OccurrenceRecord``, ordered
        by ``occurrence_id`` ascending. Expired rows are filtered out
        (not deleted — this method is read-only). All occurrences of
        one agent share a single Ed25519 ``identity``; this answers
        "which endpoints for identity X are reachable right now."
        """

    # ── v1.6.4 (CIRISPersist#70) — A0a legacy-graph migration ───────

    def run_legacy_graph_migration(self, options_json: str) -> str:
        """v1.6.4 (CIRISPersist#70) — Absorb the A0a legacy-graph
        migration. Reads ``public.graph_nodes`` + ``public.graph_edges``
        (legacy 2.8.x agent schema) and re-upserts into
        ``cirisgraph.nodes`` / ``cirisgraph.edges``.

        ``options_json`` is a JSON-encoded ``LegacyMigrationOptions``::

            {"dry_run": false,
             "attributes_cap_bytes": 1048576,
             "legacy_schema": "public",
             "stop_after_errors": 100}

        All fields optional; ``{}`` decodes to safe defaults
        (``dry_run=False``, default 1 MiB cap, ``legacy_schema="public"``,
        ``stop_after_errors=100``).

        Returns the JSON-encoded ``LegacyMigrationStats``::

            {"outcome": "ok" | "errors" | "partial",
             "nodes_read": int, "nodes_written": int,
             "nodes_skipped_already_present": int,
             "nodes_skipped_too_large": int,
             "edges_read": int, "edges_written": int,
             "edges_skipped_already_present": int,
             "edges_skipped_dangling_fk": int,
             "errors": int,
             "first_error_at_node_id": str | null,
             "first_error_message": str | null}

        ``first_error_message`` (v1.6.5, CIRISPersist#72) carries the
        human-readable text of the first error so callers can
        diagnose without bisecting.

        v1.6.5 also fixes the legacy ``timestamp without time zone``
        column type: the pre-v2.9.0 agent schema declares
        ``graph_nodes.created_at`` / ``updated_at`` as naive
        timestamps. The reader now casts them ``::text`` and parses
        both naive (UTC-assumed) and offset-bearing forms — earlier
        versions errored on every node against a real legacy
        Postgres database.

        v1.6.6 (CIRISPersist#73): legacy ``graph_edges.edge_id`` is
        arbitrary ``text``, but ``cirisgraph.edges.edge_id`` is a
        ``uuid`` column. Non-UUID legacy edge ids are now mapped to
        a deterministic UUIDv5 (valid-UUID ids pass through
        verbatim) — applied on both backends so a legacy DB migrates
        to identical edge ids regardless of target. Earlier versions
        errored on every non-UUID edge.

        Per-row decision tree:

        - Lowercase legacy scope values are normalized to UPPERCASE
          before lookup against the ``cirisgraph`` schema's CHECK
          constraint.
        - Attributes JSON is re-serialized and size-checked against
          ``attributes_cap_bytes`` (default 1 MiB). Over-cap rows
          increment ``nodes_skipped_too_large`` and do NOT call
          ``upsert_node``.
        - ``dry_run=True`` reads + parses + size-checks every row
          but does NOT write.
        - The underlying ``upsert_node`` is called with
          ``bulk_import=true`` so the graph layer's AV-45 cap is
          bypassed — this method re-checks against the operator-
          supplied bound itself so the count stays honest.
        - ``stop_after_errors=Some(n)`` halts the per-row loop once
          the error count reaches ``n`` (default 100). Partial
          progress is still returned (with ``outcome="partial"`` if
          any nodes were written, ``"errors"`` otherwise).

        Idempotent — re-running is safe (existing substrate rows
        are skipped via ``expected_version`` / PK semantics). On
        SQLite, if the legacy tables are absent (fresh install that
        never ran the 2.8.x agent), returns a zeroed-counter
        ``outcome="ok"`` so the agent's bootstrap path can proceed.

        Replaces the agent-side ``tools/ops/migrate_to_persist.py``
        psycopg2/sqlite3 reader so CIRISAgent can drop both deps
        from production ``requirements.txt`` (CIRISAgent#763 Phase 5
        close-out — the LAST raw-SQL gap in CIRISAgent 2.9.0).
        """

    # ── v1.6.0 (CIRISPersist#63) — TSDB query / prune primitives ────

    def tsdb_query_summaries(
        self,
        level: str,
        tenant_id: str,
        from_rfc3339: str,
        to_rfc3339: str,
    ) -> str:
        """v1.6.0 (CIRISPersist#63) — Return every ``MetricSummary``
        whose ``(consolidation_level, tenant_id)`` matches and whose
        ``period_start ∈ [from, to)``. Ordered by
        ``(period_start ASC, metric_name ASC)``.

        ``level`` is one of ``"basic" | "daily" | "weekly" |
        "monthly"``. ``from`` / ``to`` are RFC 3339 timestamps.
        ``to`` must be > ``from``.

        Returns the JSON-encoded ``list[MetricSummary]``. Empty list
        when no rows match (not an error).

        Backs CIRISAgent 2.9.0 Phase 3b's Basic (6h) / extensive
        (week) / profound (month) period-window queries.
        """

    def tsdb_get_summary(
        self,
        level: str,
        tenant_id: str,
        metric_name: str,
        period_start_rfc3339: str,
    ) -> str | None:
        """v1.6.0 (CIRISPersist#63) — Point-lookup of one summary by
        the deterministic ``(level, tenant_id, metric_name,
        period_start)`` key. Returns the JSON-encoded
        ``MetricSummary`` row or ``None``.
        """

    def tsdb_prune_summaries(
        self,
        level: str,
        tenant_id: str,
        before_rfc3339: str,
    ) -> int:
        """v1.6.0 (CIRISPersist#63) — Delete summary nodes whose
        ``period_end < before`` for ``(level, tenant_id)``.
        Cascades incident TEMPORAL_NEXT edges. Returns the count of
        summary nodes deleted (edges deleted silently as part of the
        cascade).

        Used by CIRISAgent 2.9.0 Phase 3b's TSDB retention sweep:
        once daily summaries roll up basic ones, the basic-tier rows
        are purged after a retention window passes.
        """

    def tsdb_count_edges_by_relationship_in_window(
        self,
        from_rfc3339: str,
        to_rfc3339: str,
    ) -> str:
        """v1.6.0 (CIRISPersist#63) — Histogram of edges within
        ``[from, to)`` grouped by ``relationship``. Filters
        ``scope='ENVIRONMENT'`` (the TSDB scope).

        Returns the JSON-encoded ``dict[str, int]``. Caller's
        ``edge_manager.py`` rolls these counts into the daily
        summary's attributes for cross-period observability.
        """

    # ── v1.6.2 (CIRISPersist#68) — non-metric typed summaries ───────

    def tsdb_consolidate_tasks(self, req_json: str) -> str:
        """v1.6.2 (CIRISPersist#68) — Consolidate task source data
        over the request's period window into a ``task_summary``
        graph node.

        ``req_json`` is a JSON-encoded ``ConsolidationRequest`` — same
        shape ``telemetry_consolidate_period`` accepts:

        .. code-block:: json

            {
              "tenant_id": "agent-datum",
              "period_start": "2026-05-19T00:00:00Z",
              "period_end":   "2026-05-19T06:00:00Z",
              "locked_by":    "tsdb-worker",
              "level":        "basic"
            }

        Aggregates ``cirislens.tasks`` (status histogram, total) +
        ``cirislens.thoughts`` (mean ``thought_depth``) over the
        window, filtered by ``agent_occurrence_id = tenant_id``.
        UPSERTs one ``task_summary`` row into ``cirisgraph.nodes``
        (scope ``ENVIRONMENT``) carrying a ``TaskSummary`` JSON
        ``attributes`` blob:

        .. code-block:: json

            {
              "tenant_id": "agent-datum",
              "period_start": "...",
              "period_end":   "...",
              "total_tasks": 42,
              "by_status": {"completed": 30, "failed": 2, ...},
              "mean_thought_depth": 1.8,
              "consolidation_level": "basic"
            }

        Returns the JSON-encoded ``TypedConsolidationOutcome``
        (``{"summary_written": bool, "source_rows": int}``).

        Final blocker for CIRISAgent 2.9.0 Phase 3b — the agent's
        TSDB pipeline emits these typed summaries alongside the
        metric ``tsdb_summary`` so the UI can surface per-period
        task / conversation / trace / audit rollups.
        """

    def tsdb_consolidate_conversations(self, req_json: str) -> str:
        """v1.6.2 (CIRISPersist#68) — Consolidate conversation-shaped
        service correlations into a ``conversation_summary`` graph
        node.

        Filters ``cirislens.service_correlations`` to rows whose
        ``action_type`` is one of ``speak | observe | speak_action |
        observe_action`` (case-insensitive). Counts total matches +
        distinct ``request_data->>'actor_id'`` over the window
        (scoped by ``agent_occurrence_id = tenant_id``).

        Emits a ``ConversationSummary`` JSON ``attributes`` blob:

        .. code-block:: json

            {
              "tenant_id": "...",
              "period_start": "...",
              "period_end":   "...",
              "total_messages": 17,
              "unique_actors": 3,
              "consolidation_level": "basic"
            }

        Returns the JSON-encoded ``TypedConsolidationOutcome``.
        """

    def tsdb_consolidate_traces(self, req_json: str) -> str:
        """v1.6.2 (CIRISPersist#68) — Consolidate trace-shaped
        service correlations into a ``trace_summary`` graph node.

        Filters ``cirislens.service_correlations`` where
        ``correlation_type = 'trace'`` over the window (scoped by
        ``agent_occurrence_id = tenant_id``). Builds a
        ``by_action_type`` histogram + total count.

        Emits a ``TraceSummary`` JSON ``attributes`` blob:

        .. code-block:: json

            {
              "tenant_id": "...",
              "period_start": "...",
              "period_end":   "...",
              "total_traces": 8,
              "by_action_type": {"call": 5, "tool_invoke": 3},
              "consolidation_level": "basic"
            }

        Returns the JSON-encoded ``TypedConsolidationOutcome``.
        """

    def tsdb_consolidate_audit(self, req_json: str) -> str:
        """v1.6.2 (CIRISPersist#68) — Consolidate audit-log rows into
        an ``audit_summary`` graph node.

        Aggregates ``cirislens.audit_log`` over the window. The
        audit_log schema uses ``tenant_id`` directly (NOT
        ``agent_occurrence_id``) and ``recorded_at`` (NOT
        ``created_at``) per the V014 column shape. Builds a
        ``by_action_type`` histogram + total count + distinct
        ``actor_id`` count.

        Emits an ``AuditSummary`` JSON ``attributes`` blob:

        .. code-block:: json

            {
              "tenant_id": "...",
              "period_start": "...",
              "period_end":   "...",
              "total_events": 12,
              "by_action_type": {"task_signed": 6, "config_changed": 2},
              "unique_actors": 4,
              "consolidation_level": "basic"
            }

        Returns the JSON-encoded ``TypedConsolidationOutcome``.
        """

    def tsdb_query_summary_nodes(
        self,
        node_type: str,
        level: str,
        tenant_id: str,
        from_rfc3339: str,
        to_rfc3339: str,
    ) -> str:
        """v1.6.2 (CIRISPersist#68) — Read typed summary nodes by
        ``node_type``. Returns a JSON ``list[dict]`` — each entry is
        the raw ``attributes`` JSON for one matching summary row.

        ``node_type`` is one of
        ``"task_summary" | "conversation_summary" |
        "trace_summary" | "audit_summary"``.

        Callers deserialize the dict per summary type
        (``TaskSummary``, ``ConversationSummary``, ``TraceSummary``,
        ``AuditSummary``) on their side — persist doesn't enforce
        the per-type Python class because the agent owns those.

        ``level`` filters ``consolidation_level``; ``tenant_id``
        matches ``attributes.tenant_id``; ``from_rfc3339`` /
        ``to_rfc3339`` bracket ``attributes.period_start``
        (half-open). Results ordered by ``period_start ASC``.

        Empty list when no rows match (not an error).
        """

    # ── v1.5.25 (CIRISPersist#65) — cirisgraph count primitives ─────

    def cirisgraph_count_nodes(self, filter_json: str) -> int:
        """v1.5.25 (CIRISPersist#65) — Count nodes matching ``filter_json``.

        ``filter_json`` is a JSON-encoded ``NodeFilter`` — same shape
        accepted by :meth:`cirisgraph_query_nodes`, including the
        v1.5.25 ``exclude`` field for the compound exclusion rule
        (``NOT (node_type = ... AND node_id LIKE ...)``) and the
        v1.6.1 ``attribute_match`` field for JSON-attribute-path
        equality / array-containment filtering:

        .. code-block:: json

            {
              "scope": "local",
              "attribute_match": {
                "path": "created_by",
                "equals_any": ["alice", "bob"],
                "array_contains_any": ["alice"]
              }
            }

        Both ``equals_any`` and ``array_contains_any`` are optional;
        when both are set they OR-combine (row matches if either arm
        does). ``path`` must be alphanumeric + underscore.

        The ``scope`` field is required (AV-47 — no implicit
        "all scopes" reads).

        Returns the raw integer (not a JSON envelope).

        Unblocks CIRISAgent 2.9.0 Phase 4
        (``COUNT(*) FROM graph_nodes`` API tile) and Phase 5
        (the agent's OBSERVER user-filter Layer 1 in
        ``memory_query_helpers.py``).
        """

    def cirisgraph_count_edges(self, scope: str) -> int:
        """v1.5.25 (CIRISPersist#65) — Count edges within ``scope``.

        ``scope`` is one of ``"local"``, ``"identity"``,
        ``"environment"``, ``"community"`` (the
        :class:`cirisgraph.GraphScope` SQL strings). Returns the raw
        integer.
        """

    def cirisgraph_count_nodes_by_type(self, scope: str) -> str:
        """v1.5.25 (CIRISPersist#65) — Group-by-type histogram of
        nodes in ``scope``.

        Returns the JSON-encoded ``dict[str, int]`` mapping
        ``node_type`` → row count. Useful for the dashboard
        "memory composition by type" tile (replacing the agent's raw
        ``SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY
        node_type`` SQL).
        """

    # ── v1.5.24 (CIRISPersist#66) — agent-detected secret store ─────

    def secrets_store_detected_secret(
        self,
        payload_json: str,
        accessor: str,
    ) -> str:
        """v1.5.24 (CIRISPersist#66) — Store an agent-detected secret
        with a **caller-supplied UUID** + full metadata bundle.

        ``payload_json`` is a JSON-encoded ``DetectedSecret`` shape:

        .. code-block:: json

            {
              "secret_uuid": "<uuid-v4>",
              "value": "<plaintext>",
              "description": "...",
              "sensitivity": "low" | "medium" | "high" | "critical",
              "detected_pattern": "regex:openai_key_v1",
              "context_hint": "in tool_args.api_key",
              "source_message_id": "msg-123",
              "auto_decapsulate_for_actions": ["tool"],
              "manual_access_only": false
            }

        Returns the JSON envelope
        ``{"outcome": "stored" | "already_claimed", "ref": <SecretReference>}``.

        ``stored`` — clean insert under the caller's UUID.
        ``already_claimed`` — same plaintext exists (content_hmac
        match across any caller path). The returned ``ref`` may
        carry a **different** ``uuid`` than the caller supplied —
        agent reconciles to the canonical id.

        Distinct from :meth:`secrets_store_secret` (manually-keyed;
        persist generates the UUID; no detection metadata) and
        :meth:`secrets_process_incoming_text` (persist's regex
        catalog detects; agent has no UUID control).

        Raises:
            ValueError: empty ``secret_uuid`` / ``value`` /
                ``detected_pattern`` / ``description``, malformed
                UUID, or ``secret_uuid`` already in use for a
                *different* plaintext (agent UUID-allocation bug).
            RuntimeError: backend / IO error.

        Replaces the agent-side ``SecretRecord`` write path in
        CIRISAgent ``secrets/store.py`` for the 2.9.0 Phase 2a
        cutover.
        """

    def trust_grant_consistency_proof(
        self,
        tenant_id: str,
        old_size: int,
        new_size: int,
    ) -> str:
        """Generate an RFC 6962 §2.1.2 consistency proof between two
        tree sizes for a tenant. Returns a JSON-encoded
        ``ConsistencyProof``."""


def reset_engine() -> None:
    """v1.10.1 (CIRISPersist#88) — handle-free reset of the
    process-singleton engine.

    Closes and un-pins whatever engine is the current process
    singleton, freeing the slot synchronously so the next
    ``Engine(...)`` constructs cleanly with any config. Unlike
    :meth:`Engine.close` it needs no ``Engine`` handle, so it
    recovers the "orphan" case — a fixture that dropped its Python
    reference without closing. A no-op when no engine is pinned;
    idempotent and safe under repeated reset/construct cycles.

    Intended for consumer test-suite isolation (call it in fixture
    teardown) and as a deterministic teardown door for in-process
    cohabitation.
    """
