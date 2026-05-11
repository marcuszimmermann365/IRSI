# Threat Model

## Purpose

This document defines the threat model for the LRSI Runtime Core V12.1.

The project is not presented as a complete AI alignment solution or as a certified
production safety system. It is a research-oriented runtime core for studying
interruptibility, auditability, human review binding, event-sourced decision
replay, and payload-bounded safety diagnostics in AI-adjacent systems.

The central safety question is:

> How can a system recognize, record, and enforce that it must not continue?

## System under analysis

The runtime executes an iterative safety pipeline around candidate proposals,
policy changes, memory updates, review decisions, and final GO / HOLD / REJECT
outcomes.

The system includes:

- a typed `IterationContext` carrying per-iteration runtime state;
- a phase pipeline with mutation, evaluation, council, review, attractor,
  adversarial, final gate, memory, observability, and persistence phases;
- `PhaseExecutor`, which emits `phase.result` events from phase outputs;
- an append-only JSONL event store with sequence numbers and hash chaining;
- optional event signing and WORM / external audit sink integration;
- materialized `run_log.json` records used as compatibility views;
- replay and projection logic for reconstructing final decisions;
- evidence bundles and signed review artifacts for human-in-the-loop review.

## Assets to protect

### Safety decisions

The final decision path must remain reliable:

- `GO` / `ACCEPT`
- `HOLD`
- `REJECT`

A rejected proposal must not be silently accepted later. A held proposal must not
be escalated without the required evidence and review conditions.

### Audit integrity

The append-only event stream must preserve:

- event order;
- event content;
- `previous_event_hash`;
- `event_hash`;
- sequence numbers;
- signature state, where enabled;
- replayability of decisions.

### Human review integrity

Human approvals, especially for soft-RED or high-risk cases, must remain bound to
the evidence that reviewers actually saw.

### Runtime state integrity

The runtime must protect:

- effective policy state;
- memory updates;
- candidate proposal provenance;
- diagnostics used by gates;
- governance mode and threshold state;
- replay-critical event references.

### Payload boundedness

Large diagnostic payloads must not recursively inflate the audit trail or cause
the audit system to become unavailable.

## Trust boundaries

### Inside the runtime

The following components are treated as internal but still testable:

- phase implementations;
- `PhaseExecutor`;
- local memory store;
- local storage adapter;
- event projection and replay code;
- diagnostic generation.

They are not assumed to be infallible. The event chain and tests are intended to
make failures visible.

### Outside the runtime

The following are outside the core trust boundary:

- LLM outputs;
- candidate proposals;
- operator input;
- reviewer identity systems;
- external storage infrastructure;
- local filesystem guarantees;
- CI/CD environment;
- deployment secrets;
- external WORM substrate;
- production key management.

### Materialized view boundary

`run_log.json` is a materialized compatibility view. It is useful for operators
and tests, but it is not the canonical audit source. The canonical audit
substrate is the append-only event stream.

## Threat categories

## T1 — Unsafe proposal acceptance

### Description

A candidate proposal that should be rejected or held reaches `ACCEPT`.

### Examples

- a proposal bypasses DGM pre-checks;
- a proposal passes evaluation but fails adversarial review;
- a proposal causes hidden policy weakening;
- a proposal creates unacceptable coupling to human attention or approval;
- a proposal appears benign but reduces future path openness.

### Mitigations

- DGM pre-check and post-check;
- council and evaluation phases;
- hold logic;
- human review phase;
- attractor analysis;
- adversarial phase;
- final gate;
- non-compensatory blocker logic;
- replayable event trail.

### Residual risk

The runtime depends on the quality of diagnostics and thresholds. Poorly
calibrated thresholds can still allow unsafe acceptance or excessive rejection.

## T2 — HOLD bypass

### Description

A proposal that enters `HOLD` is later treated as `GO` without the required
review, evidence, or gate transition.

### Examples

- review state is overwritten;
- a held decision is mutated into an accept decision;
- a downstream phase ignores `HOLD`;
- an operator manually edits a materialized record.

### Mitigations

- explicit `HOLD` state;
- human review phase;
- signed evidence bundles;
- event-sourced replay;
- committed event references;
- audit-chain verification.

### Residual risk

The project does not yet include a full external identity and authorization
system for reviewers. Production deployment requires real reviewer identity,
role binding, and key management.

## T3 — Audit tampering

### Description

A committed event, record, or evidence artifact is altered after the fact.

### Examples

- editing a JSONL event;
- deleting a prior event;
- reordering events;
- replacing event payloads;
- modifying `run_log.json` and treating it as canonical;
- replacing an evidence bundle after approval.

### Mitigations

- append-only event store;
- sequence numbers;
- hash chain;
- `previous_event_hash`;
- `event_hash`;
- event-chain verification;
- optional signing;
- optional external WORM sink;
- signed evidence bundle binding.

### Residual risk

Local filesystems cannot provide strong WORM guarantees by themselves. Production
use requires an independently controlled immutable audit substrate.

## T4 — Payload-bloat attack

### Description

A proposal or diagnostic path causes recursive or extremely large payloads,
making the audit system slow, expensive, or unavailable.

### Examples

- embedding full history into phase diagnostics;
- embedding events inside records and records inside events;
- recursively serializing large phase outputs;
- poisoning memory with large payloads;
- causing denial of service through audit growth.

### Mitigations in V12.1

- compact diagnostic histories;
- committed event references instead of embedded events;
- large payload summaries and hashes;
- `audit.iteration_record` summary events instead of full record mirroring;
- regression tests for log growth and event size.

### Residual risk

Payload budgets should be made configurable and enforced in all new phases.

## T5 — Review-bypass or review-forgery

### Description

The system accepts a high-risk decision without valid human review, or attaches
review approval to evidence the reviewer did not actually inspect.

### Examples

- synthetic approval artifacts;
- stale approval reused for a different proposal;
- unsigned review bundle;
- review performed by a non-authorized reviewer;
- single-person approval where two-person review is required.

### Mitigations

- evidence bundle binding;
- signed review artifacts;
- two-person review path;
- production-mode signing requirements;
- audit trail of review-related phase results.

### Residual risk

Reviewer identity, authentication, authorization, and organizational separation
of duties must be implemented in deployment infrastructure.

## T6 — Replay divergence

### Description

Replay reconstructs a different final decision than the original runtime
decision, or cannot reconstruct the decision at all.

### Examples

- phase events are missing;
- legacy phase names are not recognized;
- event references are provisional rather than committed;
- materialized records disagree with committed event stream;
- event schemas drift without migration.

### Mitigations

- committed event references stored in records;
- event-chain verification;
- replay and projection tests;
- support for legacy phase names where needed;
- schema validation in event verification.

### Residual risk

Replay compatibility must be maintained whenever phase names, event schemas, or
decision semantics change.

## T7 — Memory poisoning

### Description

A proposal or model output writes harmful or misleading information into memory,
influencing later decisions.

### Examples

- false safety claims added to memory;
- adversarial instructions stored as facts;
- policy weakening persisted as learned state;
- diagnostic state confused with durable memory.

### Mitigations

- memory gate;
- memory consolidation phase;
- final decision dependency;
- audit of memory events;
- rejection and hold paths before memory persistence.

### Residual risk

The project needs more dedicated memory-poisoning benchmarks and formal memory
admissibility tests.

## T8 — Self-modification boundary violation

### Description

The runtime accepts or applies unsafe self-modification.

### Examples

- mutation changes safety gates;
- mutation weakens audit;
- mutation disables review;
- mutation modifies thresholds without traceability;
- mutation bypasses DGM constraints.

### Mitigations

- mutation phase;
- DGM pre-check;
- pre-proposal adversarial phase;
- DGM post-check;
- final gate;
- persistence audit.

### Residual risk

This is an experimental self-modification boundary, not a mathematically proven
safe self-modifying system.

## T9 — Deceptive compliance and proxy alignment

### Description

A proposal appears aligned under direct evaluation but optimizes a proxy or hides
unsafe consequences.

### Examples

- deceptive safety language;
- shallow compliance with review criteria;
- proxy optimization that harms path openness;
- silent narrowing of future options;
- hidden dependency on human attention or trust.

### Mitigations

- adversarial phase;
- proxy integrity diagnostics;
- silence monitoring;
- sham resonance detection;
- attractor analysis;
- human coupling checks;
- final gate.

### Residual risk

Adversarial diagnostics remain heuristic and require ongoing empirical
calibration.

## T10 — External sink failure

### Description

The runtime believes audit events have been externally persisted, but the sink is
unavailable, inconsistent, or compromised.

### Examples

- local WORM directory is writable;
- S3 Object Lock misconfigured;
- event store unavailable;
- pending journal not reconciled;
- external sink silently drops events.

### Mitigations

- external sink abstraction;
- pending journal;
- fail-closed production mode;
- local WORM validation;
- sink reconciliation tests.

### Residual risk

Production reliability depends on real infrastructure guarantees and operational
monitoring.

## Out of scope

This project does not currently solve:

- model-weight security;
- training-time alignment;
- full identity and access management;
- distributed consensus for audit storage;
- certified safety proofs;
- formal verification of all phase logic;
- secure enclave deployment;
- adversarial robustness of the underlying LLM;
- legal or regulatory certification.

## Security assumptions

The runtime assumes:

1. Python execution environment is not fully compromised.
2. Production signing keys are protected outside the repository.
3. External WORM infrastructure is independently governed.
4. Operators do not treat `run_log.json` as the canonical source.
5. Reviewer identity and access control are supplied by deployment environment.
6. New phases preserve the safety invariants described in
   `docs/SAFETY_INVARIANTS.md`.

## Recommended next research steps

1. Add explicit adversarial benchmark scenarios.
2. Add configurable payload budgets for all new event types.
3. Add formal invariant tests for HOLD / REJECT non-escalation.
4. Add memory-poisoning and review-bypass red-team suites.
5. Add external sink chaos tests.
6. Add schema-versioned replay compatibility tests.
7. Add deployment-specific key management guidance.
