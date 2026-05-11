# LRSI Project V12.0

V12.0 converts the production-near phase runtime into an **event-sourced runtime**.  The materialized `run_log.json` remains available for compatibility, but every phase now emits a runtime event and the append-only event stream is the primary replay substrate.

## What changed in V12.0

- every `PhaseResult` automatically emits a `phase.result` runtime event;
- `Storage` now writes both the materialized iteration record and an append-only `*.events.jsonl` event stream;
- `eventsourcing.py` provides:
  - `RuntimeEvent`,
  - `AppendOnlyEventStore`,
  - strict event-chain verification,
  - event projection,
  - decision replay from events,
  - event-stream sealing;
- `EvidenceBundle` case files are now hash-bound and can be HMAC/Ed25519 signed;
- two-person review can bind approvals to a signed evidence bundle;
- WORM/external sink integration is available through `ExternalAuditSink` and `LocalWORMDirectorySink`;
- replay can reconstruct final decisions from `audit.iteration_record` and `phase.result` events.

## Run

```bash
python -m compileall -q .
python -m pytest -q -rs
python stress_tests_v120_event_sourced_runtime.py
make check
```

A normal run writes:

```text
run_log.json
run_log.json.events.jsonl
memory_store.json
```

`run_log.json` is a compatibility/materialized view.  The event stream is the V12 canonical runtime audit substrate.

## Event replay

```python
from storage import Storage

storage = Storage("run_log.json")
projection = storage.project_events()
replay = storage.replay_decisions()
ok, errors = storage.verify_event_chain()
```

## WORM/external sink

For local validation of write-once behavior:

```bash
AUDIT_WORM_DIR=/tmp/lrsi-worm python runner.py
```

Each committed event is mirrored through the write-once sink contract.  Production deployments should replace the local sink with S3 Object Lock, EventStoreDB, Kafka with governed retention, or an equivalent independently controlled audit substrate.

## Signed Evidence Bundles

Set one of the signing modes before generating review case files:

```bash
AUDIT_SIGNING_MODE=hmac AUDIT_HMAC_KEY=dev-secret python runner.py
# or
AUDIT_SIGNING_MODE=ed25519 AUDIT_ED25519_PRIVATE_KEY=<base64-key> AUDIT_SIGNER_ID=runtime-1 python runner.py
```

Soft-RED approvals can be bound to the signed evidence bundle via the two-person review gate.

## Status

V12.0 is a **production-near event-sourced runtime**, not a fully certified production safety system.  Remaining deployment obligations include external WORM infrastructure, key management, real reviewer identity, calibrated thresholds and broad live-LLM validation.

## Key documents

- `docs/V12_0_EVENT_SOURCED_RUNTIME.md`
- `docs/EVENT_STORE_SPEC.md`
- `docs/SIGNED_EVIDENCE_REVIEW.md`
- `docs/V11_6_RUNTIME_OPERATIONS_MIGRATION.md`
