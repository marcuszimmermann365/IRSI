# V10.6 Iteration Notes

V10.6 implements the requested P0 and P1 items as a structural/runtime-hardening iteration. It intentionally avoids adding another safety heuristic layer.

## P0 implemented

1. **Agent/LLMClient decoupling**
   - `Agent` now accepts an injected `llm_client`.
   - Evaluation no longer calls `deepcopy(agent)`.
   - Probe agents are created via `Agent.fork()`, which snapshots prompt/policy/memory but reuses the same LLM client reference.
   - This prevents fragile or expensive deep copies of live API clients.

2. **PipelineExecution further split**
   - Added `AdversarialPhase`, `MemoryConsolidationPhase`, and `PostRunReporter` in `pipeline/phase_services.py`.
   - `PipelineExecution.run_adversarial_layers()` now delegates the full DREL/A3/A4/Pareto/Sham/Carrier/Complexity/Auxiliary block to `AdversarialPhase`.
   - Memory consolidation and post-run reporting are also delegated.

3. **Audit backend abstraction**
   - `Storage` is now a compatibility facade over pluggable audit backends.
   - `JSONAuditBackend` remains the default development backend.
   - `AppendOnlyAuditBackend` writes JSONL append-only audit events and can maintain a materialized JSON file for legacy tools.
   - Existing hash-chain verification remains compatible.

4. **LLM errors are first-class metrics**
   - `evaluate()` now returns `llm_error_count`, `llm_error_rate`, `fixture_miss_count`, and `fixture_miss_rate`.
   - Outputs carry `llm_error` and `fixture_miss` flags.
   - `__LLM_ERROR__` no longer appears only as a bad string answer; it is measurable runtime evidence.

## P1 implemented

1. **Static tools are executed in CI**
   - CI now runs `ruff check`, `bandit`, and `mypy` over the V10.6 contract/runtime surface.

2. **IterationContext narrowed by phase contexts**
   - Added `pipeline/phase_contexts.py`.
   - Introduced `AdversarialPhaseContext` and `AuditPhaseContext` as narrow projections from the large compatibility `IterationContext`.

3. **Structured logging instead of runtime print()**
   - Added `lrsi_logging.py`.
   - Runtime library use is quiet by default.
   - CLI/legacy verbose output is available through `verbose=True` or `LRSI_VERBOSE=1`.

4. **Live fixture recording path**
   - Added `scripts/record_live_fixtures.py`.
   - Added `llm_fixtures/LIVE_FIXTURE_README.md` and example fixture schema.
   - No external live API credentials were available in the build environment, so the ZIP does not claim to contain newly captured external live responses.

## Validation

Native pytest:

```text
44 passed, 1 skipped
```

Segmented executable suites through V10.6 passed in validation. A full `run_all_suites.sh` run is long in this environment, so V10.0–V10.6 contract suites were also executed individually.
