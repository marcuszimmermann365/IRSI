# LRSI V11.6 — Runtime Operations Migration

V11.6 moves the operational runtime seams into the declarative phase model. The
objective is production-near operability, not a new safety heuristic layer.

## Migrated phases

### EvaluationPhase

`EvaluationPhase` exposes candidate evaluation as a first-class audited phase.
For compatibility with the V11.5 self-modification boundary, it reuses existing
child metrics when `DGMPrecheckPhase` has already evaluated the candidate. If no
child metrics exist, it runs the evaluator explicitly.

The phase emits:

- `llm_error_count`
- `llm_error_rate`
- `fixture_miss_count`
- `fixture_miss_rate`
- output count
- whether existing metrics were reused

### MemoryConsolidationPhase

Memory consolidation is no longer hidden inside
`apply_or_reject_candidate()`. It is a declarative phase with explicit inputs,
immutable output and automatic phase audit.

The phase emits:

- extracted memory count
- consolidated count
- review count
- rejected count
- memory events

### ObservabilityPhase

`ObservabilityPhase` emits structured runtime events and creates a simple trace
projection over prior phase audit entries.

The phase emits:

- spans, one per prior phase audit entry
- runtime metrics
- structured `iteration_completed` event
- trace id propagation

## Trace ID propagation

Each `IterationContext` now receives a trace id with the format:

```text
lrsi-<16 hex chars>
```

The trace id is included in:

- final audit record
- every automatic phase audit entry
- evaluation diagnostics
- memory diagnostics
- observability events
- runtime event block

## Audit and hash-chain behavior

The new runtime operations block is included in the persisted audit record:

```json
"runtime_operations_v11_6": {
  "evaluation": {},
  "memory_consolidation": {},
  "observability": {},
  "runtime_events": []
}
```

Because the block is present before persistence, it is protected by the existing
`record_hash` / `previous_record_hash` chain.

## Compatibility stance

V11.6 preserves existing V10–V11.5 contract behavior. The migration is structural:
Evaluation, Memory and Observability now have typed phase boundaries, but the
underlying safety decisions remain unchanged.
