# V11.3 Safe Phase Migration

V11.3 implements the first planned migration wave after the V11.2 phase-runtime seam. The goal is not to introduce new gates, but to reduce hidden coupling in the runtime.

## Migrated phases

The following phases now expose explicit input contracts and return immutable `PhaseResult` patches when executed by `PhaseExecutor`:

- `HoldLogicPhase` / `HoldLogicPhaseInput`
- `HumanReviewPhase` / `HumanReviewPhaseInput`
- `FinalGatePhase` / `FinalGatePhaseInput`
- `PersistencePhase` / `PersistencePhaseInput`
- `PostRunReporter` / `PostRunReporterInput`

`CouncilPhase` remains the reference migration from V11.2. Remaining complex phases (`Mutation`, `DGM`, `Attractor`, `Adversarial`, `Evaluation`, `Memory`) remain candidates for subsequent waves.

## Audit seam

Every migrated runtime phase returns a `PhaseResult`. The `PhaseExecutor` derives the phase audit entry automatically from the result. `PersistencePhase` is special: to keep the persistence phase event inside the hash-protected audit record, it marks its result with `audit_already_in_patch=True` and includes the persistence audit entry in the record before hashing/signing.

## Compatibility

Legacy keyword-call behavior is retained for `HumanReviewPhase`, `FinalGatePhase` and `PostRunReporter` so older contract tests and migration scripts remain executable during the transition. The declarative loop uses the typed-input path.

## Remaining migration waves

Recommended next steps:

1. V11.4: Attractor and Adversarial diagnostics with nested typed outputs.
2. V11.5: Mutation, PreProposalAdversarial, DGMPrecheck and DGMPostcheck.
3. V11.6: Evaluation, Memory and Observability.
4. V12.0: event-sourced runtime with context projection from audit events.
