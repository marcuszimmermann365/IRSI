# V11.0 Release Notes

## Objective

V11.0 addresses the safety-critical gaps identified in V10.6 and shifts the artifact toward a production-near runtime system.

## P0 delivered

1. Fixed review-mode persistence crash.
2. Added regression test for review-mode HOLD persistence.
3. Made audit hash-chain verification strict by default.
4. Added tests for missing hashes and tampered audit records.

## P1/P2 delivered

1. `AdversarialPhase` now returns a complete result object and does not implicitly mutate the shared `IterationContext`.
2. Added local reproducibility target: `make check`.
3. Added optional HMAC audit signatures.
4. Added machine-readable threshold registry.
5. Added production-near runtime, audit, human-review, and operations documentation.

## Known limits

- HMAC signatures are local integrity aids, not a substitute for independent key management or an external write-once audit sink.
- Threshold values remain prototype defaults.
- Reviewer identity must be bound by a real deployment adapter.
- LLM live-mode testing requires provider credentials and fixture recording outside this artifact build.
