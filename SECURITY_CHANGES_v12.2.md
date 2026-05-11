# Security Changes v12.2.0

## Sprint 3: Property-Based Tests + Further Hardening + v12.2 Preparation

v12.2.0 raises the assurance level of the runtime by adding randomized
property-based tests, improving critical-path diagnostics, and preparing the
project for a cleaner release cycle.

## 1. Property-based testing

Added `tests/test_v122_property_based_security.py` with Hypothesis coverage
for:

- event-chain integrity after blocked mutations;
- tamper detection in committed event streams;
- `PreProposalAdversarialPhase` RED/YELLOW/GREEN boundary behavior;
- RED pre-proposal state combined with attempted ACCEPT/GO;
- HOLD-state mutation blocking;
- Council-RED hard-stop semantics;
- DGM pre-check respect for pre-proposal blocks.

## 2. Better invariant diagnostics

`InvariantViolation` now carries:

- invariant code;
- original message;
- structured context;
- context-key summary in the exception string.

This makes failing security conditions easier to diagnose in tests, CI logs,
and future operational telemetry.

## 3. Structured security logs

Critical logs in `eventsourcing.py`, `storage.py`, and `invariants.py` now
include more explicit fields such as:

- `trace_id`;
- `iteration`;
- `decision`;
- `phase`;
- `reason`;
- `event_hash`;
- `previous_event_hash`;
- `record_hash`;
- `block_reason`;
- production/externalization state.

The loggers remain quiet-by-default via `NullHandler`.

## 4. SECURITY and AUDIT logging levels

v12.2.0 introduces symbolic log levels:

- `SECURITY = 35`
- `AUDIT = 25`

These levels allow downstream operators to route security-critical runtime
signals differently from ordinary debug or info logs.

## 5. Version and release preparation

- `version.py` updated to `12.2.0`.
- `pyproject.toml` updated to `12.2.0`.
- `hypothesis>=6.100` added to dev dependencies.
- `CHANGELOG.md` created/extended.
- `OPERATIONS.md` added.

## Validation

Minimum validation target:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```
