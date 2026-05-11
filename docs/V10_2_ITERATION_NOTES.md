# LRSI v10.2 Iteration Notes

V10.2 is a consolidation iteration on top of V10.1. It does not add a new
safety heuristic. It reduces meta-complexity by moving more runner boundaries
behind explicit contracts and by closing small operability gaps identified in
static review.

## Implemented changes

1. **Further runner stage seams**
   - Added `EvaluationStage`, `AttractorStage`, `DRELStage`, `A3Stage`,
     `A4Stage`, `ExtendedGateStage`, and `PersistenceStage`.
   - `runner.py` now uses these stages for evaluation, attractor anchoring,
     A2/A3/A4 checks, final extended decision, and persistence.
   - The long runner is still not fully decomposed, but the most error-prone
     additional seams now have typed outputs.

2. **Runtime records are versioned before persistence**
   - Normal records now include `schema_version` at construction time, not only
     when `Storage.log_iteration()` enriches them.
   - This makes `return_records=True` and persisted records follow the same
     audit contract.

3. **Memory read-modify-write locking**
   - `MemoryStore` mutations now reload the latest JSON state under lock,
     mutate that state, then atomically write it back.
   - This closes the stale-writer overwrite window for normal MemoryStore APIs.
   - JSON remains a prototype persistence layer, not a production database.

4. **Typed Human Override classes**
   - Added `DecisionClass`: `soft_red`, `hard_red`, `immutable_red`, and
     `external_integrity_red`.
   - Human `APPROVE` can only move `soft_red` toward acceptance.
   - `hard_red`, `immutable_red`, and `external_integrity_red` cannot be
     approved into GREEN by human override. Reject and force-hold remain allowed.

5. **Fixture mode no longer depends on current working directory**
   - Default fixtures are resolved via package resources, with source-tree
     fallback relative to `llm_client.py`.
   - `llm_fixtures` is now a package and its JSON fixture is included as package data.

6. **CI static-check surface activated**
   - CI now runs Ruff and Bandit on the v10.2 contract surface.
   - This is intentionally scoped to the actively hardened files rather than
     the entire legacy research prototype.

## Still open

- Full extraction of every remaining branch in `runner.py`.
- Empirical calibration of thresholds.
- Real signed human-review UI/CLI.
- Tamper-evident append-only audit/event store.
- Larger real-response fixture corpus.
- Broader Ruff/Bandit/Mypy rollout across all legacy files.
