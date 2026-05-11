# V11.0 Operations Checklist

## Before running

- [ ] Set explicit `storage_path` and `memory_path`.
- [ ] Choose `AUDIT_BACKEND`.
- [ ] For signed local audit, set `AUDIT_HMAC_KEY` from a secret manager.
- [ ] Use `LLM_MODE=fixture` for deterministic validation.
- [ ] Use `LLM_MODE=live` only with provider credentials and rate-limit monitoring.
- [ ] Run `make check`.

## After each run

- [ ] Load returned records and persisted records; they should match.
- [ ] Run `verify_hash_chain(records)`.
- [ ] If signatures are enabled, run `verify_hash_chain(records, require_signature=True, signature_key=...)`.
- [ ] Inspect all non-GO final decisions as non-success states.
- [ ] Archive audit records to an external sink.

## Release hygiene

- [ ] Run `make clean` before packaging.
- [ ] Ensure no `__pycache__`, `.pytest_cache`, runtime logs, or secrets are in release artifacts.
- [ ] Include docs and threshold registry.
