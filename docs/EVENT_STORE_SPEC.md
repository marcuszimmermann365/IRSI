# Event Store Specification

## Event schema

Each runtime event contains:

```text
event_id
schema_version
event_type
phase
iteration
trace_id
stream_id
sequence
previous_event_hash
event_hash
created_at
payload
optional event_signature metadata
```

`event_hash` is computed over the canonical event body excluding signature fields.  `previous_event_hash` forms a strict chain.

## Event types

- `phase.result`: generated from every `PhaseResult`.
- `audit.iteration_record`: generated when the materialized audit record is persisted.

## Verification

```python
from eventsourcing import verify_event_chain
ok, errors = verify_event_chain(events, require_signature=False)
```

With signing enabled, use `require_signature=True`.  In production mode (`production_mode=True` or `LRSI_PRODUCTION_MODE=1`), the event store requires `AUDIT_SIGNING_MODE=hmac` or `ed25519`, a configured signing adapter, and `AUDIT_WORM_DIR` or an injected external sink.

## Sealing

`AppendOnlyEventStore.seal_sequence()` computes a Merkle root over ordered event hashes and can write the seal to an external sink.
