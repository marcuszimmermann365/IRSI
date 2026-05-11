# Architecture — LRSI Runtime Core v12.1.0

## Overview

LRSI is a phase-based, event-sourced runtime for studying interruptibility,
auditability, replayable decisions, human review binding, and self-modification
boundaries in AI-adjacent systems.

The runtime is organized around:

- typed phase inputs and `PhaseResult` outputs;
- an `IterationContext` carrying state across phases;
- a `PhaseExecutor` that applies explicit patches and emits audit events;
- an append-only event store as canonical audit substrate;
- a materialized `run_log.json` compatibility view;
- replay and projection utilities for decision reconstruction.

## Main runtime flow

The high-level phase sequence is:

1. Review Mode
2. Mutation
3. Pre-proposal Adversarial
4. DGM Pre-check
5. Evaluation
6. Council
7. Hold Logic
8. Human Review
9. Erosion & Human Coupling
10. Attractor Analysis
11. Adversarial Phase
12. DGM Post-check
13. Final Gate
14. Apply or Reject Candidate
15. Memory Consolidation
16. Post-decision Accounting
17. Observability
18. Persistence

## Self-Modification Boundary

The self-modification boundary is the safety-critical segment that controls
whether a candidate prompt/policy/runtime mutation may enter the broader
governance pipeline.

It consists of:

```text
Mutation
  -> PreProposalAdversarialPhase
  -> DGMPrecheckPhase
  -> downstream governance/evaluation phases
```

### Kill-switch

`PreProposalAdversarialPhase` is the earliest hard boundary for dangerous
mutations. If its decision is `RED`, it returns a terminal `PhaseResult`:

```text
decision: RED
terminal: true
patch.mutation_blocked: true
patch.block_reason: <reason>
```

This prevents the mutation from reaching DGM pre-check or final gate through
normal pipeline execution.

### Defense in depth

`DGMPrecheckPhase` also checks for `mutation_blocked=True`. This protects
direct calls, future refactors, tests, and accidental bypasses of the normal
terminal path.

### Central invariants

`invariants.py` defines the hard rules that must remain true across future
development. These invariants are used by tests and storage-time validation.
Violations raise `InvariantViolation` and emit structured logs.

Current invariants include:

- no RED pre-proposal acceptance;
- blocked mutations must be terminal;
- DGM pre-check must respect pre-proposal blocks;
- no mutation without pre-proposal adversarial coverage;
- final gate must respect blocked state;
- event chain must verify after a block;
- HOLD mode must not apply mutations;
- council RED must lead to STOP/REJECT/ROLLBACK semantics.

### Audit representation

The self-modification boundary is visible in:

- `phase_audit`;
- `phase.result` events;
- `event_refs_v12`;
- final materialized record summaries;
- structured security logs.

### Failure semantics

A boundary failure is not treated as a normal low-score outcome. It is a
hard safety condition. The runtime should prefer `HOLD`, `STOP`, or `REJECT`
over continuing with an uncertain or unsafe mutation.

## Event-sourced audit spine

Every meaningful `PhaseResult` emits a `phase.result` runtime event. Events
are committed through `AppendOnlyEventStore`, which assigns sequence numbers,
previous-event hashes, and event hashes.

`run_log.json` remains useful for human inspection but is a materialized
compatibility view. The event stream is the canonical audit substrate.

## Observability

Sprint 2 adds structured logs in three namespaces:

- `lrsi.security.invariants`
- `lrsi.security.eventsourcing`
- `lrsi.security.storage`

These logs are JSON-like and contain decision context, phase, iteration,
reason, terminal state, block state, event hashes, record hashes, and replay
or verification status where applicable.


## Property-based security layer

v12.2.0 adds Hypothesis-based property tests as a randomized assurance
layer around the Self-Modification Boundary and event-sourced audit spine.

The properties focus on:

- event-chain integrity under random decision sequences;
- tamper detection after blocked mutations;
- RED/YELLOW/GREEN pre-proposal boundary behavior;
- RED-to-GO/ACCEPT bypass attempts;
- HOLD-state mutation blocking;
- Council-RED hard-stop semantics;
- DGM pre-check respect for pre-proposal blocks.

These tests complement the deterministic regression suite. They are not a
formal proof, but they increase coverage over state combinations that are
easy to miss with example-based tests alone.


## v13.0.0 release architecture notes

The v13.0.0 architecture treats `security_errors.py`, `invariants.py`, `eventsourcing.py`, and `storage.py` as the release-critical security spine.
