# Changelog

## v13.2.0 — Contributor Onboarding and IterationContext Refactoring Plan

### Added

- Rewritten `CONTRIBUTING.md` with quickstart, good-first-issue guidance, workflow, security-sensitive areas, and new-phase rules.
- `docs/good-first-issues.md` with 10 ready-to-copy contributor issues.
- Future `IterationContext` refactoring proposal in `pipeline/runner_core.py`.

### Changed

- Version bumped to `13.2.0` in `version.py` and `pyproject.toml`.
- Schema-version compatibility tests updated for `13.2.0`.

### Compatibility

- No runtime behavior changes.
- Existing flat `IterationContext` remains intact.
- Refactoring proposal is documentation/commentary only and is not wired into execution.


## v13.0.0 — Final Security Hardening and Release Preparation

### Added

- 14 property-based security tests in `tests/test_v122_property_based_security.py`.
- Property coverage for event-chain load, tamper attempts, logging integrity,
  multi-stage blockade paths, and simultaneous invariant violations.
- Unified `LRSISecurityError` base class in `security_errors.py`.
- Additional invariants:
  - `assert_terminal_security_event_is_non_accepting(...)`
  - `assert_blocked_record_effective_policy_unchanged(...)`
  - `assert_event_refs_match_phase_audit(...)`
- `INVARIANTS.md`.
- `CONTRIBUTING.md`.
- `LICENSE` using Apache License 2.0.
- `SECURITY_CHANGES_v13.0.md`.

### Changed

- Version bumped to `13.0.0`.
- README rewritten for release-readiness.
- Security-relevant event-store and storage failures now use `LRSISecurityError`
  or a subclass instead of generic runtime exceptions.
- `InvariantViolation` now subclasses `LRSISecurityError`.
- Storage performs additional pre-commit and post-event-reference invariant checks.
- Operations documentation expanded for logging and production-mode guidance.
- Architecture and security model documents updated for v13.0.

### Security

- Stronger central error handling for invariant violations.
- More explicit fail-closed behavior around blocked mutations.
- Better detection of terminal GO/ACCEPT inconsistency.
- Better detection of blocked mutations changing effective policy.
- Better detection of materialized records whose event refs do not cover phase audit.
- Property tests now exercise randomized RED/YELLOW/GREEN combinations and tamper paths.

## v12.2.0 — Property-Based Security Hardening and Release Preparation

### Added

- Hypothesis property-based tests for event-chain integrity, pre-proposal boundary,
  invariant combinations, HOLD-state behavior, Council-RED behavior, and DGM block respect.
- `OPERATIONS.md`.
- `SECURITY_CHANGES_v12.2.md`.

### Changed

- Version bumped to `12.2.0`.
- `hypothesis>=6.100` added to dev dependencies.
- Invariant messages and critical structured logs gained richer context fields.
- `SECURITY` and `AUDIT` logging levels introduced.

## v12.1.0 — Security Hardening: Kill-Switch and Central Invariants

### Added

- Hard kill-switch in `PreProposalAdversarialPhase`.
- `mutation_blocked=True`, `block_reason`, and `terminal=True` for RED pre-proposal decisions.
- Root-level `invariants.py`.
- `InvariantViolation`.
- DGM pre-check blocked-state defense-in-depth.

### Changed

- Version bumped to `12.1.0`.
- Tests updated to reflect earlier pre-proposal terminal behavior.

## v12.1 Sprint 2 — Extended Invariants and Observability

### Added

- Additional invariants for mutation coverage, final gate blocked-state respect,
  event-chain integrity after block, HOLD mutation blocking, and Council-RED semantics.
- Structured security logging in `invariants.py`, `eventsourcing.py`, and `storage.py`.
- `SECURITY_MODEL.md`.
- `ARCHITECTURE.md`.

### Changed

- Security loggers became quiet-by-default via `NullHandler`.
- Storage validates selected central invariants before committing iteration records.

## v12.0 / v12.1 Payload Hardening Baseline

### Added

- Event-sourced runtime spine.
- Append-only JSONL event store.
- Hash-chain verification.
- Committed event references in materialized records.
- Payload-bounded event summaries and references.
- CLI parameters for runtime execution.
