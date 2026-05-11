# Publication Notes

## Recommended repository positioning

Use this phrasing in the GitHub repository description or project overview:

> A research-oriented event-sourced AI safety runtime for STOP/HOLD/GO control,
> human review binding, audit-chain verification, replayable decisions, and
> payload-bounded diagnostics.

## Recommended disclaimer

> This project is experimental. It is intended for research, review, and
> controlled evaluation. It is not a certified production safety system and does
> not claim to solve AI alignment.

## Recommended first paragraph

LRSI Runtime Core V12.1 is an experimental runtime framework for studying how
AI-adjacent systems can interrupt unsafe continuation, bind human review to
evidence, preserve tamper-evident audit trails, and replay final decisions from
an event-sourced record.

The project starts from a narrow but important alignment question:

> How does a system recognize that it must not continue?

## Recommended public claims

Good claims:

- research-oriented runtime core;
- experimental AI safety control plane;
- production-near but not production-certified;
- event-sourced audit and replay;
- STOP / HOLD / GO decision control;
- human review binding;
- payload-bounded diagnostics;
- interruptibility and non-compensatory blockers.

Avoid claims:

- solves AI alignment;
- guarantees safe AI;
- production-certified;
- mathematically proven safe;
- autonomous governance solution;
- secure against all adversaries.

## Suggested X / Twitter post

```text
AI alignment is often framed as a question:

How do we make systems do the right thing?

I built a small runtime core that starts with a different question:

How does a system recognize that it must not continue?

STOP/HOLD/GO.
Audit instead of trust.
Interruption instead of optimization rush.

Not a product.
More like a disturbance signal.

[GitHub link]
```

## Suggested extended GitHub summary

This repository explores a runtime layer for AI safety research. Instead of
treating safety as a single score, the system decomposes proposal handling into
explicit phases: mutation, evaluation, council, hold logic, human review,
attractor analysis, adversarial diagnostics, final gate, memory consolidation,
observability, and persistence.

V12.1 adds payload hardening so that audit records remain operationally usable:
large diagnostics are summarized and hash-referenced, materialized records store
committed event references, and the event stream remains the canonical source for
replay.

The code is intended for scientific and security-oriented development, including
red-team scenarios, replay tests, audit-chain verification, review-binding
experiments, and interruptibility research.

## Suggested reader path

For new readers:

1. `README.md`
2. `docs/RESEARCH_POSITIONING.md`
3. `docs/THREAT_MODEL.md`
4. `docs/SAFETY_INVARIANTS.md`
5. `docs/RED_TEAM_BENCHMARKS.md`
6. `docs/EVENT_STORE_SPEC.md`
7. `docs/SIGNED_EVIDENCE_REVIEW.md`
8. `docs/PRODUCTION_RUNTIME_GUIDE.md`

## Suggested issue labels

- `research`
- `threat-model`
- `safety-invariant`
- `benchmark`
- `red-team`
- `replay`
- `audit`
- `human-review`
- `payload-hardening`
- `production-readiness`
- `good-first-experiment`

## Suggested first GitHub issues

1. Add benchmark scenario JSON fixtures for the first ten red-team cases.
2. Add configurable payload budget enforcement across all phase events.
3. Add replay fixture tests for schema-version compatibility.
4. Add memory-poisoning red-team suite.
5. Add review-bypass red-team suite.
6. Add external WORM sink integration example.
7. Add phase-extension guide for research contributors.
8. Add false accept / false hold / false reject metrics.
