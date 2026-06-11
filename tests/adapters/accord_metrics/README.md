# accord_metrics test domain

## Tombstone — 2.9.6 LensCore fold (CIRISAgent#866 / #857)

The trace-emit pipeline (partial-trace assembly, attempt indexing, JCS
canonicalization, Ed25519 signing, consent gating, local-copy tee, lens
HTTP reject/discard semantics, orphan sweep, persistence) moved into the
`ciris-lens-core` Rust substrate. The Python internals those tests covered
no longer exist in `ciris_adapters/ciris_accord_metrics/services.py`, and
their coverage now lives in CIRISLensCore's Rust test suite
(`src/capture/*` tests) with the wire shape frozen in
`CIRISLensCore/docs/PUBLIC_SCHEMA_CONTRACT.md`.

Retired files and where the coverage moved:

| Retired file | What it covered | Coverage now |
|---|---|---|
| `test_trace_signature_canonical.py` | JCS (RFC 8785) canonical bytes, signed-payload field set, deployment_profile pinning, Ed25519 sign/verify round-trip | CIRISLensCore `src/capture/*` Rust tests + PUBLIC_SCHEMA_CONTRACT.md (signing rides persist's `engine.signer()`) |
| `test_attempt_index_and_new_events.py` | attempt_index counters/cleanup (substrate-owned now); `_extract_component_data` gating tests were carried into `test_accord_metrics_service.py` | attempt-index: CIRISLensCore `src/capture/*`; extraction gating: `test_accord_metrics_service.py` here |
| `test_local_copy_tee.py` | local-copy tee write/sequence/failure-isolation, byte-equality with wire bytes | CIRISLensCore `src/capture/*` (Gap 4 tee) — agent-side env wiring kept in `test_accord_metrics_service.py` |
| `test_lens_reject_discard.py` | `LensContentRejectError` + HTTP 4xx/5xx re-queue vs discard branches | obsolete by design — the bespoke HTTP shipping path is retired (#857, "no second shipping mechanism"); typed rejection is now the `{"outcome": "rejected"}` capture_event contract, covered in `test_accord_metrics_service.py` |

Also removed from `test_accord_metrics_service.py` in the same fold:
`CompleteTrace` / `TraceComponent` / `Ed25519TraceSigner` / `TestJCSCutover`
dataclass and signer tests (symbols deleted from services.py), the event
queue / batch / flush tests, and `record_pdma_decision` tests.

## What lives here now

- `test_accord_metrics_service.py` — agent-side semantic mapping: event
  normalization → `LensClient.capture_event` component shape, outcome
  bookkeeping, `_extract_component_data` trace-level gating, consent state,
  metrics shape, lifecycle (lens-core is a REQUIRED substrate leg).
- `test_accord_metrics_adapter.py` — unconditional registration (consent
  gates sharing at the substrate seal, not registration), consent API.
- `test_lens_fold_integration.py` — real `ciris_persist.Engine` + real
  `LensClient` through `AccordMetricsService.start()`. Marked xfail on
  CIRISLensCore#43 (LensClient needs the Engine capsule handshake in pip
  cohabitation); auto-greens when the fixed wheel lands (strict=False).
