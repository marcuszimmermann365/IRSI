# Research Positioning

## One-sentence description

LRSI Runtime Core V12.1 is a research-oriented runtime framework for studying
AI safety mechanisms such as interruptibility, auditability, human review
binding, replayable decisions, payload-bounded event sourcing, and
non-compensatory STOP / HOLD / GO control.

## What this project is

This project is best understood as an experimental runtime substrate.

It is designed to make the following question operational:

> How does a system recognize, record, and enforce that it must not continue?

The runtime does not attempt to solve all of AI alignment. Instead, it focuses on
a narrower and testable layer: decision-time safety control around proposals,
policy changes, memory updates, and runtime mutations.

## What this project is not

This project is not:

- a complete AI alignment solution;
- a model-training method;
- a proof of safe AGI;
- a certified production safety system;
- a replacement for human governance;
- a legal or regulatory compliance framework;
- a secure identity and access management system;
- a guarantee that unsafe model behavior will always be detected.

## Why this matters

Many AI safety discussions focus on how to make systems pursue the right goals.
This project focuses on a complementary runtime question:

> Even if goals, prompts, policies, or evaluations are imperfect, can the runtime
> detect when continuation itself has become unsafe?

The project therefore emphasizes:

- interruption before unsafe optimization;
- audit instead of implicit trust;
- human review binding;
- non-compensatory blockers;
- event-sourced reconstruction;
- payload-bounded observability;
- replayable final decisions.

## Research hypothesis

The core research hypothesis is:

> AI safety requires not only better objectives, but runtime mechanisms that can
> interrupt, hold, reject, audit, and replay decision paths before unsafe
> optimization becomes irreversible.

This hypothesis can be decomposed into testable sub-hypotheses:

1. A phase-structured runtime makes safety failures easier to locate.
2. Event-sourced decisions improve auditability and forensic analysis.
3. Payload-bounded diagnostics are necessary for operational audit integrity.
4. Human review becomes more meaningful when bound to signed evidence.
5. HOLD states are safety-relevant and should not be treated as mere errors.
6. Replayable decisions improve post-hoc accountability.
7. Non-compensatory blockers are needed where weighted scoring would hide
   unacceptable failure modes.

## Relationship to AI alignment

The project is aligned with AI alignment research, but it addresses a specific
runtime layer rather than the entire field.

Useful framing:

> LRSI Runtime Core is an experimental control plane for studying how AI-adjacent
> systems can stop, hold, reject, audit, and replay safety-critical decisions.

Avoid framing:

> This solves AI alignment.

Better public claim:

> This is a small research runtime for studying interruptibility, auditability,
> human oversight, and replayable safety decisions.

## Research questions

### RQ1 — Interruptibility

Can the system reliably enter `HOLD` or `REJECT` when continuation would increase
risk?

Suggested experiments:

- unsafe optimization proposal;
- review-bypass attempt;
- memory-poisoning attempt;
- self-modification boundary violation;
- deceptive compliance proposal.

### RQ2 — Auditability

Can a third party reconstruct why a final decision was made?

Suggested experiments:

- replay from event stream only;
- deletion of materialized view;
- tampered event stream;
- missing terminal event;
- malformed phase event.

### RQ3 — Human review binding

Can human approval be bound to specific evidence rather than to vague runtime
state?

Suggested experiments:

- stale approval reuse;
- evidence modified after approval;
- one reviewer used twice;
- unsigned approval in production mode.

### RQ4 — Payload hardening

Can safety diagnostics remain useful without making the audit trail operationally
unbounded?

Suggested experiments:

- large proposal payload;
- deeply nested diagnostic object;
- repeated multi-iteration run;
- history recursion attempt;
- event-size regression test.

### RQ5 — Replay stability

Can replay reconstruct final decisions without live model calls or mutable
external state?

Suggested experiments:

- replay in clean environment;
- replay after memory deletion;
- replay after schema migration;
- replay across phase-name aliases.

### RQ6 — Non-compensatory safety

Can the runtime prevent high-risk blockers from being hidden by high scores in
unrelated dimensions?

Suggested experiments:

- strong evaluation score with audit failure;
- strong utility score with review failure;
- strong performance score with path-openness failure;
- high confidence with proxy-integrity failure.

## Suggested paper abstract

LRSI Runtime Core V12.1 is an experimental event-sourced runtime for studying
decision-time safety controls in AI-adjacent systems. The system decomposes
proposal handling into explicit phases, emits committed runtime events, verifies
an append-only hash chain, binds human review to evidence artifacts, and
reconstructs final decisions through replay. The core design investigates a
complementary alignment question: not only how to make systems pursue correct
objectives, but how to make continuation interruptible, auditable, and
non-compensatory under uncertainty. V12.1 introduces payload hardening to prevent
recursive audit growth and to preserve operational replayability. The project is
not a complete alignment solution or certified production safety system; it is a
research substrate for red-team scenarios, runtime safety invariants, audit
integrity tests, and human-in-the-loop control experiments.

## Suggested GitHub repository description

A research-oriented event-sourced AI safety runtime for STOP/HOLD/GO control,
human review binding, audit-chain verification, replayable decisions, and
payload-bounded diagnostics.

## Suggested README warning

> This project is experimental. It is intended for research and security review,
> not for direct deployment as a certified safety system.

## Suggested X / Twitter description

AI alignment is often framed as: how do we make systems do the right thing?

This project starts with another question:

How does a system recognize that it must not continue?

STOP/HOLD/GO.  
Audit instead of trust.  
Interruption before optimization rush.

## Evaluation dimensions

A research team can evaluate the runtime along these dimensions:

| Dimension | Core question |
|---|---|
| Interruptibility | Does the runtime stop or hold unsafe continuation? |
| Auditability | Can decisions be reconstructed? |
| Tamper evidence | Does event-chain verification detect manipulation? |
| Review binding | Is human approval bound to evidence? |
| Payload boundedness | Does audit growth remain operational? |
| Replay determinism | Does replay avoid live mutable dependencies? |
| Non-compensation | Can hard blockers override attractive scores? |
| Memory safety | Are memory updates gated by final decision? |
| Self-modification control | Are mutations constrained by pre/post checks? |
| Production fail-closed behavior | Does production mode refuse weak audit setups? |

## Recommended public positioning

Use restrained language:

- "research runtime"
- "experimental substrate"
- "production-near, not production-certified"
- "audit and replay framework"
- "interruptibility and HOLD/STOP control"
- "AI safety mechanism study"

Avoid inflated language:

- "solves alignment"
- "safe AGI runtime"
- "guaranteed trustworthy AI"
- "fully autonomous governance"
- "certified security system"

## Development priorities for research teams

1. Formalize threat model and safety invariants.
2. Add benchmark scenarios.
3. Add adversarial test fixtures.
4. Add external WORM integration examples.
5. Add human-review identity integration examples.
6. Add replay compatibility fixtures.
7. Add payload budget enforcement across all phases.
8. Add structured metrics for false accept, false reject, and false hold.
9. Add documentation for extending phases safely.
10. Add minimal reproducible experiments suitable for publication.
