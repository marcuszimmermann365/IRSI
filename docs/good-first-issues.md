# Good First Issues

These issues are intentionally small, well-scoped, and suitable for new contributors.

## 1. Add comprehensive type hints to `invariants.py`

**Labels:** `good first issue`, `refactor`

Add or improve type hints for helper functions and invariant functions in `invariants.py`.

Acceptance criteria:

- No behavior changes.
- Existing tests remain green.
- Type hints improve readability without making the code harder to use from tests.

## 2. Create Mermaid diagrams for the full phase pipeline

**Labels:** `documentation`, `good first issue`

Create one or more Mermaid diagrams showing the runtime phase flow.

Suggested files:

- `docs/phase-flow.md`
- or an additional section in `ARCHITECTURE.md`

Acceptance criteria:

- Diagram includes Mutation, PreProposal, DGM Pre-check, Final Gate, Persistence.
- Diagram distinguishes GO / HOLD / REJECT paths.

## 3. Improve docstrings in `pipeline/runner_core.py`

**Labels:** `documentation`

Improve docstrings around `PipelineRunner`, `IterationContext`, and major runtime methods.

Acceptance criteria:

- No behavior changes.
- Docstrings explain ownership of safety, audit, governance, and metric fields.

## 4. Add 5 new property-based tests for the self-modification boundary

**Labels:** `testing`

Extend Hypothesis coverage for RED/YELLOW/GREEN combinations and blocked-state transitions.

Acceptance criteria:

- At least 5 new property-based tests.
- Tests cover at least one new edge case involving blocked mutation state.
- `python -m pytest tests/test_v122_property_based_security.py -q` passes.

## 5. Extract `SafetyContext` and `GovernanceContext` from `IterationContext`

**Labels:** `refactor`, `good first issue`

Start the incremental `IterationContext` refactor by adding small parallel dataclasses.

Acceptance criteria:

- Add new dataclasses in `pipeline/phase_contexts.py`.
- Keep existing flat fields intact.
- Add tests showing backward compatibility.

## 6. Add example usage in `README.md`

**Labels:** `documentation`

Add a small runner example with expected output and a short explanation of generated artifacts.

Acceptance criteria:

- Example shows `runner.main(...)`.
- Mentions `run_log.json` and `run_log.json.events.jsonl`.
- Keeps claims restrained.

## 7. Write a tutorial: “How to add a new phase”

**Labels:** `documentation`, `help wanted`

Create a tutorial that explains how to add a decision-relevant phase safely.

Suggested file:

- `docs/how-to-add-a-phase.md`

Acceptance criteria:

- Covers typed input, `PhaseResult`, bounded diagnostics, event emission, tests, and invariants.
- Includes a small example phase.

## 8. Increase test coverage of `storage.py` verify functions

**Labels:** `testing`

Add tests for storage verification and replay paths.

Acceptance criteria:

- Covers both valid and tampered event stores.
- Covers materialized records with event references.
- Existing storage tests remain green.

## 9. Add structured logging examples in `OPERATIONS.md`

**Labels:** `documentation`

Add examples for enabling `lrsi.security.*` logs.

Acceptance criteria:

- Shows a simple `logging.StreamHandler`.
- Mentions `SECURITY` and `AUDIT` levels.
- Explains that loggers are quiet by default.

## 10. Create a visual overview of the event-sourcing flow

**Labels:** `documentation`

Create a Mermaid or ASCII diagram for the event-sourcing spine.

Acceptance criteria:

- Shows `PhaseResult -> RuntimeEvent -> AppendOnlyEventStore -> verify -> replay`.
- Mentions `event_hash` and `previous_event_hash`.
- Links back to `eventsourcing.py` and `OPERATIONS.md`.
