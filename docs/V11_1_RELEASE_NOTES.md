# V11.1 Release Notes — Operational Validation Runtime

V11.1 implements the requested shift from logic development toward runtime operationalization.

## Implemented

1. **Audit hardening**
   - Ed25519 public-key signing adapter.
   - Legacy HMAC signing retained.
   - External `ExternalAuditSink` contract.
   - Local write-once validation sink.
   - Merkle seal generation over record hashes.
   - `Storage.seal_sequence(...)` bridge.

2. **Threshold calibration foundation**
   - Shadow-mode decision recorder.
   - False-positive / false-negative analyzer with confidence intervals.
   - Threshold backtesting harness for historical records.
   - Threshold registry updated to schema 11.1.

3. **HITL / Evidence Bundle**
   - Structured case files for HOLD/RED/STOP-style decisions.
   - Change proposal, prompt/policy diff, active thresholds, DREL diagnostics and council counterarguments included.
   - Two-person signed review gate added for practical validation.

4. **Truth sensitivity / semantic drift**
   - Deterministic local semantic drift monitor.
   - External embedding-provider seam.
   - Mini adversarial pre-proposal orchestrator.
   - Runtime records now carry `semantic_drift` and `preproposal_adversarial`.

## Boundary

V11.1 does not claim full production safety. It provides executable seams that production deployments can connect to WORM storage, identity systems, signing services, calibrated datasets and real reviewer interfaces.
