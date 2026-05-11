# Central Invariants — LRSI v13.0.0

The runtime currently defines 11 central security invariants in `invariants.py`.

## Invariants

1. `assert_preproposal_not_red_and_accepted(...)`
   - A RED pre-proposal state must never coexist with acceptance.

2. `assert_mutation_blocked_has_terminal(...)`
   - A blocked mutation must be terminal.

3. `assert_dgm_precheck_respects_block(...)`
   - DGM pre-check must not pass a mutation already blocked upstream.

4. `assert_no_mutation_without_preproposal_check(...)`
   - Mutation-bearing states require pre-proposal adversarial coverage.

5. `assert_final_gate_respects_blocked_state(...)`
   - Final gate must not accept a blocked mutation.

6. `assert_event_chain_integrity_after_block(...)`
   - A block must be represented in a valid event chain.

7. `assert_hold_mode_blocks_all_mutations(...)`
   - HOLD states must not apply mutations or consolidate memory.

8. `assert_council_red_always_leads_to_stop(...)`
   - Council RED must lead to STOP/REJECT/ROLLBACK semantics.

9. `assert_terminal_security_event_is_non_accepting(...)`
   - Terminal security events must not carry GO/ACCEPT semantics.

10. `assert_blocked_record_effective_policy_unchanged(...)`
    - A blocked mutation must not change the effective policy.

11. `assert_event_refs_match_phase_audit(...)`
    - Event references in materialized records must cover phase audit.

## Error behavior

Violations raise `InvariantViolation`, which subclasses `LRSISecurityError`.
Each violation includes an invariant code and structured context.

## Logging behavior

Invariant violations emit structured events through:

```text
lrsi.security.invariants
```

Storage also logs pre-commit invariant failures through:

```text
lrsi.security.storage
```

## Development rule

New phases that can affect acceptance, mutation, policy, memory, or audit must
either preserve these invariants or introduce an explicit new invariant and
corresponding tests.
