# Audit Sealing and WORM Sink Contract

V11.1 introduces `audit_sinks.py` and `signing.py`.

## ExternalAuditSink

Implement this interface for production sinks:

```python
class ExternalAuditSink:
    sink_name: str
    def write_once(self, event_id: str, payload: dict) -> dict: ...
```

Suitable implementations include S3 Object Lock, EventStoreDB, Kafka with governed retention, or an internal write-once ledger.

## Sealing

`AuditSealService` computes a Merkle root over ordered `record_hash` values.

```python
from storage import Storage
from audit_sinks import LocalWORMDirectorySink

storage = Storage("run_log.json")
seal = storage.seal_sequence(
    external_sink=LocalWORMDirectorySink("runtime/worm"),
    sequence_id="daily-2026-05-10",
)
```

The local sink validates the contract but is not a production WORM store.

## Signing

Recommended validation mode:

```bash
AUDIT_SIGNING_MODE=ed25519
AUDIT_ED25519_PRIVATE_KEY=<base64 raw32 or base64 PEM>
AUDIT_SIGNER_ID=runtime-node-a
```

HMAC remains available for compatibility:

```bash
AUDIT_HMAC_KEY=change-me
```
