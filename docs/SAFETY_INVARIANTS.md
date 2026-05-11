# Safety Invariants

## Purpose

This document defines the safety invariants that should remain true across future
development of the LRSI Runtime Core V12.1.

These invariants are intended to guide implementation, testing, review, and
research. They are not a formal proof of safety. They are engineering and
research constraints that make safety regressions visible.

## Vocabulary

### Proposal

A candidate policy, prompt, memory, behavior, or runtime change evaluated by the
pipeline.

### Decision

The final or intermediate decision state assigned to a proposal. The principal
states are:

- `GO`
- `ACCEPT`
- `HOLD`
- `REJECT`

The codebase may use both `GO` and `ACCEPT` in different layers. New code should
make the mapping explicit.

### Canonical event stream

The append-only `*.events.jsonl` event stream produced by the runtime event
store. It is the canonical audit source.

### Materialized view

`run_log.json`, or any derived record, projection, dashboard, or report. A
materialized view must not be treated as canonical audit truth.

## Core invariants

## I1 — Canonical audit source invariant

The append-only event stream is the canonical audit substrate.

`run_log.json` is a materialized view and must not be used as the sole source of
truth for safety-critical replay.

### Required tests

- event-chain verification passes for valid streams;
- event-chain verification fails after event edit, deletion, or reordering;
- replay reconstructs final decisions from committed events.

## I2 — Append-only event invariant

Committed events must not be modified in place.

Each committed event must preserve:

- sequence number;
- event type;
- phase name, where applicable;
- timestamp;
- payload;
- `previous_event_hash`;
- `event_hash`;
- signature state, where enabled.

### Required tests

- editing one event breaks verification;
- deleting one event breaks verification;
- reordering events breaks verification;
- recomputing a later event without a valid chain is detected.

## I3 — Committed reference invariant

Records may store references to committed events, but must not rely on
provisional pre-commit events.

Each event reference stored in a materialized record should include at least:

- `event_id`;
- `sequence`;
- `event_hash`;
- `event_type`;
- `phase_name`, if applicable.

### Required tests

- record event references match committed event stream entries;
- no record uses `sequence = 0` for all events unless the stream has exactly one
  event;
- replay uses committed event data, not provisional local event objects.

## I4 — Payload boundedness invariant

Runtime events must remain payload-bounded.

Large diagnostics, history, phase outputs, or evidence artifacts should be
represented through:

- compact summaries;
- hashes;
- byte counts;
- stable references;
- external evidence artifacts where appropriate.

Events must not recursively embed:

- full iteration history;
- full prior records;
- full event streams;
- full phase output objects when summaries suffice.

### Required tests

- maximum event size remains below a configured threshold;
- multi-iteration run size grows approximately linearly;
- no phase event contains full `history`;
- `audit.iteration_record` does not mirror entire record payloads.

## I5 — Non-escalation of REJECT invariant

A `REJECT` decision must not silently become `ACCEPT` or `GO`.

A rejected proposal may only be reconsidered as a new proposal with a new audit
trail.

### Required tests

- rejected proposal is not applied to effective policy;
- rejected proposal does not create durable memory updates unless explicitly
  marked as rejected diagnostic memory;
- replay reconstructs rejection;
- no downstream phase overrides rejection without a new proposal identity.

## I6 — HOLD requires resolution invariant

A `HOLD` decision must not become `GO` or `ACCEPT` without an explicit,
auditable resolution path.

Resolution may require:

- human review;
- two-person approval;
- signed evidence bundle;
- additional diagnostics;
- threshold adjustment;
- governance-mode transition.

### Required tests

- held proposal remains held without review evidence;
- stale review evidence cannot resolve a new hold;
- review evidence is bound to the proposal or evidence bundle hash;
- replay reconstructs the hold and the resolution path.

## I7 — Human review binding invariant

Human approval must be bound to the evidence that was reviewed.

Approval artifacts should include:

- reviewer identity or signer identifier;
- timestamp;
- evidence bundle hash;
- proposal identifier;
- decision;
- review mode;
- signature, where enabled.

### Required tests

- modifying evidence after approval invalidates binding;
- approval for one proposal cannot be reused for another proposal;
- two-person review requires distinct valid approvals where configured;
- production mode rejects unsigned approval artifacts where signing is required.

## I8 — Production fail-closed invariant

Production mode must fail closed if required audit controls are unavailable.

In production mode, the runtime should require:

- signed events;
- external or WORM audit sink;
- valid signing configuration;
- event-chain verification;
- sink reconciliation where applicable.

### Required tests

- production mode fails without signing configuration;
- production mode fails without WORM/external sink where required;
- failed sink writes are recorded in pending journal or block progress;
- reconciliation detects missing external events.

## I9 — Replay determinism invariant

For a fixed committed event stream and schema version, replay must reconstruct
the same final decisions.

Replay must not depend on:

- mutable local memory outside the event stream;
- current wall-clock time;
- live LLM calls;
- environment-specific operator state;
- `run_log.json` contents not derivable from events.

### Required tests

- replay succeeds after deleting materialized view;
- replay result is stable across repeated runs;
- replay does not call external LLMs;
- replay detects missing or malformed terminal events.

## I10 — Phase event coverage invariant

Every runtime phase that materially affects the decision path must emit a
`phase.result` event.

Terminal paths, early rejection paths, review-mode paths, and DGM pre-check
failures must not skip event coverage.

### Required tests

- sample runs contain events for all expected phases;
- terminal early-exit paths produce audit events;
- phase coverage script passes;
- new phases are added to the phase registry and event coverage tests.

## I11 — Diagnostic separation invariant

Runtime decision payload, diagnostic payload, and evidence payload should remain
separated.

A phase output should distinguish:

1. decision-relevant summary;
2. bounded diagnostics;
3. external or hash-referenced evidence artifacts.

### Required tests

- phase result payloads contain bounded decision summaries;
- large evidence is stored by reference;
- diagnostic payloads cannot alter final decisions after commit;
- evidence references include hashes.

## I12 — Memory admissibility invariant

Memory updates must be gated and auditable.

A rejected or held proposal must not create ordinary durable memory updates that
make the proposal effectively active.

### Required tests

- rejected proposal does not write active memory;
- held proposal writes only diagnostic or pending memory, if any;
- memory events are linked to final decision;
- memory consolidation is replay-visible.

## I13 — Self-modification boundary invariant

Self-modification must pass through explicit proposal, pre-check, adversarial,
post-check, and final-gate phases.

No mutation may directly alter:

- audit controls;
- review requirements;
- DGM checks;
- final gate logic;
- payload bounds;
- event signing;
- replay verification.

### Required tests

- mutation cannot disable review gates without rejection or hold;
- mutation cannot disable event emission;
- mutation cannot bypass DGM pre-check;
- mutation cannot alter production fail-closed behavior silently.

## I14 — Threshold traceability invariant

Threshold changes must be auditable and attributable.

Thresholds must not drift silently through implicit state changes.

### Required tests

- threshold adjustments appear in event or record summaries;
- governance-mode transitions are logged;
- replay can identify which threshold set affected a decision;
- threshold changes require review where configured.

## I15 — Schema-version compatibility invariant

Event schemas and record schemas must remain versioned.

Breaking schema changes require:

- migration notes;
- replay compatibility tests;
- explicit version bump;
- backward-compatible parsing where possible.

### Required tests

- old event stream fixtures can still be verified or intentionally rejected with
  clear migration errors;
- phase-name aliases are maintained where needed;
- schema version is present in emitted events.

## Implementation guidance for new phases

Every new phase should define:

1. phase name;
2. typed input contract;
3. typed output or `PhaseResult`;
4. decision effect;
5. event payload summary;
6. diagnostic payload bounds;
7. evidence artifact references, if any;
8. replay relevance;
9. failure behavior;
10. tests for event emission and payload size.

## Suggested invariant test matrix

| Invariant | Unit test | Integration test | Red-team test |
|---|---:|---:|---:|
| Canonical audit source | yes | yes | yes |
| Append-only events | yes | yes | yes |
| Committed references | yes | yes | no |
| Payload boundedness | yes | yes | yes |
| REJECT non-escalation | yes | yes | yes |
| HOLD resolution | yes | yes | yes |
| Human review binding | yes | yes | yes |
| Production fail-closed | yes | yes | yes |
| Replay determinism | yes | yes | yes |
| Phase event coverage | yes | yes | no |
| Memory admissibility | yes | yes | yes |
| Self-modification boundary | yes | yes | yes |

## Minimal release gate

A release should not be considered publication-ready unless:

```text
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

Additional recommended checks:

```text
ruff check .
mypy .
bandit -r .
```

Where these tools are unavailable, the release notes should explicitly state
that they were not run in the local environment.
