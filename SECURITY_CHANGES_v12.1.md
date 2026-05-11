# Security Changes v12.1.0

## Sprint 1: Security Hardening — Kill-Switch + Central Invariants

This release hardens the self-modification boundary.

## 1. Pre-proposal kill-switch

`PreProposalAdversarialPhase` now fails closed when the phase decision is
`RED`.

A RED result now sets:

- `terminal=True`
- `mutation_blocked=True`
- `block_reason=<RED reason>`

This prevents dangerous mutations from entering the DGM pre-check and the
downstream governance pipeline.

## 2. Improved trace entries

Pre-proposal trace entries now explicitly record:

- blocker list;
- warning list;
- maximum pre-proposal severity;
- whether the mutation was blocked;
- whether the phase was terminal;
- the kill-switch reason.

## 3. Central safety invariants

A new root module `invariants.py` defines central safety guards:

- `assert_preproposal_not_red_and_accepted(...)`
- `assert_mutation_blocked_has_terminal(...)`
- `assert_dgm_precheck_respects_block(...)`

Violations raise `InvariantViolation`.

## 4. DGM pre-check block guard

Normal runtime execution stops before DGM pre-check when the pre-proposal
kill-switch fires. As an additional defense-in-depth measure, DGM pre-check
now also refuses a state that already carries `mutation_blocked=True`.

## 5. Version

Runtime/package version updated to `12.1.0`.

## Validation target

Minimum checks:

```bash
python -m compileall -q .
python -m pytest -q -rs
```


# Sprint 2: Extended Security Invariants + Observability

## Added invariants

Sprint 2 extends `invariants.py` to at least eight central safety
invariants:

- `assert_no_mutation_without_preproposal_check(...)`
- `assert_final_gate_respects_blocked_state(...)`
- `assert_event_chain_integrity_after_block(...)`
- `assert_hold_mode_blocks_all_mutations(...)`
- `assert_council_red_always_leads_to_stop(...)`

## Structured logging

Added structured security logging in:

- `eventsourcing.py`
- `storage.py`
- `invariants.py`

Critical events now include contextual fields such as iteration, phase,
decision, reason, terminal state, mutation block state, event hashes, and
record hashes.

## Documentation

Added:

- `SECURITY_MODEL.md`
- `ARCHITECTURE.md`
