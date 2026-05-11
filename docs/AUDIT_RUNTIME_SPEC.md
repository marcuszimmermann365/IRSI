# Audit Runtime Specification

## Record requirements

Every V11.0 audit record must include:

```text
schema_version
run_id
created_at
audit_event_type
previous_record_hash
record_hash
```

`verify_hash_chain(records)` fails closed when either hash field is missing.

## Legacy compatibility

Legacy unhashed records are accepted only by explicit opt-in:

```python
verify_hash_chain(records, allow_legacy_unhashed=True)
```

This mode is for migration/forensics, not production verification.

## Optional local signing

Set `AUDIT_HMAC_KEY` before writing records. The storage layer adds:

```text
audit_signature_algorithm = HMAC-SHA256(record_hash)
audit_signature
```

Verification:

```python
verify_hash_chain(records, require_signature=True, signature_key="...")
```

## Production note

HMAC signing improves local tamper evidence but does not create independent audit trust. Production deployments should forward each record to an external append-only or WORM sink and bind signatures to a managed key identity.
