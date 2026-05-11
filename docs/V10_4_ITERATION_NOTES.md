# V10.4 Iteration Notes

## Objective

The requested non-negotiable point was: **structure the 1000-line runner core into real phases**.

V10.3 made `runner.main()` thin. V10.4 goes one level deeper: the former long `_run_pipeline_legacy_semantics()` loop is replaced by `PipelineExecution`, whose `run_iteration()` method is an explicit phase orchestrator.

## Main implementation

New/changed runtime structures:

- `IterationContext` dataclass: per-iteration contract surface
- `PipelineExecution`: owns runtime state and phase methods
- `_run_pipeline_legacy_semantics()`: now a compatibility wrapper only

Core phase methods:

```text
prepare_iteration
run_mutation_contract
run_council
run_hold_logic
run_human_review
run_erosion_and_human_coupling
run_attractor_checks
run_adversarial_layers
run_final_gate
apply_or_reject_candidate
persist_iteration_record
```

## Design choice

The refactor is deliberately conservative. It avoids introducing a new safety heuristic or changing decision semantics while making the execution order inspectable and testable. This protects the accumulated V9/V10 invariant history from accidental behavior changes.

## Tests added

- `stress_tests_v104_contracts.py`
- `tests/test_v104_contracts.py`

The tests assert:

- schema version is 10.4
- required phase methods exist
- `_run_pipeline_legacy_semantics()` is short and delegates
- `run_iteration()` orchestrates the phase list and remains short
- `IterationContext` has safe defaults
- a one-iteration smoke run still produces a versioned record and core trace phases

## Still open

V10.4 does not solve empirical calibration, signed human review, or production-grade audit storage. Those remain next-step concerns after structural decomposition.
