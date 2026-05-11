# V10.5 Iteration Notes

V10.5 implements the next review's two mandatory priorities:

1. **Audit consistency** — records returned by `return_records=True` are now the exact storage-enriched audit records written to disk.
2. **Runner decoupling** — critical phase responsibilities are delegated from `PipelineExecution` to small phase-service classes with typed result dataclasses.

V10.5 intentionally adds no new safety heuristic layer. It is a structural and audit-contract iteration.

## 1. Audit consistency closed

Before V10.5, `PipelineExecution.persist_iteration_record()` appended the raw runtime record to `self.all_records` and then called `Storage.log_iteration()`. The persisted record received `run_id`, `created_at`, `previous_record_hash`, `record_hash`, and `audit_event_type`, but the in-memory record returned through `return_records=True` did not.

V10.5 changes `PersistenceStage.run()` so that it returns the storage-enriched record:

```python
class PersistenceStage:
    def run(self, *, storage, record: dict) -> dict:
        return storage.log_iteration(record)
```

All runner paths now append the persisted representation to `self.all_records`, including:

- normal iteration records
- review-mode records
- DGM pre-check rejection records

This means:

```text
return_records=True == JSON audit log contents
```

for the same run.

## 2. Phase-service decoupling

V10.4 made the iteration order explicit. V10.5 moves high-risk phase logic into service classes in `pipeline/phase_services.py`:

```text
CouncilPhase
HumanReviewPhase
FinalGatePhase
AuditRecorder
```

`PipelineExecution` still owns orchestration and long-lived dependencies, but these responsibilities are no longer embedded as large inline methods:

```text
run_council()       -> CouncilPhase.run(...)
run_human_review() -> HumanReviewPhase.run(...)
run_final_gate()   -> FinalGatePhase.run(...)
persist...         -> AuditRecorder.persist(...)
```

Each service returns a typed dataclass result, e.g. `CouncilPhaseResult`, `HumanReviewPhaseResult`, `FinalGatePhaseResult`, or `AuditRecordResult`.

## 3. Tests added

New suites:

```text
stress_tests_v105_contracts.py
tests/test_v105_contracts.py
```

They verify:

- schema version is 10.5
- `PersistenceStage.run()` returns enriched audit records
- returned records equal the persisted JSON log
- hash-chain verification passes over returned records
- `PipelineExecution` owns phase-service instances
- runner phase methods delegate to those services

## 4. Non-goals

V10.5 does not claim production readiness. The following remain open:

- empirical threshold calibration
- machine-readable threshold register
- signed human review
- external append-only audit store
- larger real-LLM fixture corpus
- broader typed record model beyond the new phase result contracts
- broader static analysis over legacy modules

V10.5 is a maintainability and audit-contract release, not a production certification.
