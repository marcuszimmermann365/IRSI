# Security Changes v13.0.0

## Summary

v13.0.0 consolidates the security hardening performed since v12.0 into a
release-ready research runtime.

The main security theme is fail-closed self-modification:

> A system may not continue merely because it can continue.

## Improvements since v12.0

### Event-sourced audit spine

- append-only JSONL event stream;
- sequence numbers;
- `previous_event_hash`;
- `event_hash`;
- event-chain verification;
- event projection and decision replay;
- materialized records store committed event references.

### Payload hardening

- large diagnostics are summarized or hash-referenced;
- recursive record/event/history embedding is avoided;
- `audit.iteration_record` writes compact summaries;
- payload growth is bounded by regression tests.

### Self-modification kill-switch

- `PreProposalAdversarialPhase` RED is terminal;
- RED sets `mutation_blocked=True`;
- RED sets `block_reason`;
- DGM pre-check also refuses blocked states.

### Central invariants

v13.0.0 includes 11 central invariants:

- `assert_preproposal_not_red_and_accepted`
- `assert_mutation_blocked_has_terminal`
- `assert_dgm_precheck_respects_block`
- `assert_no_mutation_without_preproposal_check`
- `assert_final_gate_respects_blocked_state`
- `assert_event_chain_integrity_after_block`
- `assert_hold_mode_blocks_all_mutations`
- `assert_council_red_always_leads_to_stop`
- `assert_terminal_security_event_is_non_accepting`
- `assert_blocked_record_effective_policy_unchanged`
- `assert_event_refs_match_phase_audit`

### Unified security errors

- `LRSISecurityError` introduced in `security_errors.py`;
- `InvariantViolation` now subclasses `LRSISecurityError`;
- event-store and storage security failures use the unified hierarchy;
- storage logs invariant failures centrally before re-raising.

### Property-based tests

v13.0.0 includes 14 property-based security tests covering:

- event-chain integrity;
- event-chain behavior under load;
- tamper attempts;
- RED/YELLOW/GREEN pre-proposal combinations;
- RED → ACCEPT/GO bypass attempts;
- multi-stage blockades;
- logging integrity;
- simultaneous invariant violations.

### Structured security logs

Critical paths now emit structured logs with:

- `trace_id`;
- `iteration`;
- `decision`;
- `phase`;
- `reason`;
- `event_hash`;
- `previous_event_hash`;
- `record_hash`;
- `block_reason`.

Loggers remain quiet-by-default.

## Remaining limitations

- This is not a formal proof of safety.
- This is not certified for production deployment.
- Reviewer identity and access control remain external responsibilities.
- WORM guarantees depend on infrastructure.
- LLM and diagnostic quality remain empirical risks.
