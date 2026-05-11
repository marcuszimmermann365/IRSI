# Security Model — LRSI Runtime Core v12.1.0

## Scope

The LRSI runtime is a research-oriented AI safety control plane. It does not
claim to solve AI alignment and is not a certified production safety system.
Its security model focuses on runtime control of self-modification,
interruptibility, auditability, replay, and human-review binding.

The central question is:

> Should this system be allowed to continue?

## Core safety states

The runtime uses three practical control outcomes:

- `GO` / `ACCEPT`: the proposal may continue;
- `HOLD`: the proposal must not continue without further review or evidence;
- `STOP` / `REJECT`: the proposal is blocked.

Sprint 1 made pre-proposal RED states terminal. Sprint 2 adds broader
invariants and structured observability around those decisions.

## Self-modification boundary

Self-modification is only admissible through an explicit sequence:

1. mutation creation;
2. pre-proposal adversarial check;
3. DGM pre-check;
4. evaluation and council;
5. hold / human review;
6. adversarial diagnostics;
7. DGM post-check;
8. final gate;
9. event-sourced persistence.

A RED result in `PreProposalAdversarialPhase` now acts as a kill-switch:

- `terminal=True`;
- `mutation_blocked=True`;
- `block_reason=<reason>`;
- no downstream acceptance is allowed.

## Central invariants

The root module `invariants.py` defines the current central invariants:

1. `assert_preproposal_not_red_and_accepted(...)`
2. `assert_mutation_blocked_has_terminal(...)`
3. `assert_dgm_precheck_respects_block(...)`
4. `assert_no_mutation_without_preproposal_check(...)`
5. `assert_final_gate_respects_blocked_state(...)`
6. `assert_event_chain_integrity_after_block(...)`
7. `assert_hold_mode_blocks_all_mutations(...)`
8. `assert_council_red_always_leads_to_stop(...)`

Invariant violations raise `InvariantViolation` and are logged as structured
security events through `lrsi.security.invariants`.

## Audit and event chain

The canonical audit substrate is the append-only event stream
`*.events.jsonl`.

The materialized `run_log.json` is a compatibility view. It is not the
canonical source for replay or integrity.

Critical events are logged through `lrsi.security.eventsourcing`, including:

- terminal phase results;
- RED / STOP / HOLD / REJECT decisions;
- blocked mutation events;
- event schema validation failures;
- production append verification failures.

## Storage observability

`storage.py` logs structured events through `lrsi.security.storage` for:

- iteration persistence start;
- iteration persistence completion;
- critical decision persistence;
- blocked mutation event-chain verification.

Before committing an iteration record, storage enforces central invariants
for mutation coverage, blocked-state acceptance, HOLD-state mutation
application, and council-RED semantics.

## Fail-closed assumptions

The security model is fail-closed for the following conditions:

- RED pre-proposal result;
- blocked mutation passed to DGM pre-check;
- blocked mutation accepted by final gate;
- mutation without pre-proposal adversarial coverage;
- HOLD state that applies a mutation;
- council RED softened into GO/HOLD/ACCEPT;
- broken event chain after a block.

## Residual risks

This model still depends on:

- calibration quality of diagnostics;
- quality of adversarial checks;
- external identity and authorization for reviewers;
- production-grade key management;
- actual WORM/external audit infrastructure;
- continued replay compatibility across schema versions.

## Validation

Minimum validation for this security model:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```


## v12.2.0 update

v12.2.0 adds property-based assurance for the security model. Randomized
tests now exercise event-chain integrity, pre-proposal RED/YELLOW/GREEN
boundary behavior, RED-to-ACCEPT bypass attempts, HOLD mutation blocking,
Council-RED hard-stop behavior, and DGM respect for blocked states.

Critical-path errors and logs now carry more explicit decision context:
`trace_id`, `iteration`, `decision`, `phase`, `reason`, event hashes,
record hashes, and block reasons.


## v13.0.0 update

v13.0.0 introduces `LRSISecurityError`, expands the invariant set to 11, and adds property tests for load, logging integrity, tamper attempts, and simultaneous invariant violations.
