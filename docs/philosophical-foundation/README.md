# Philosophical Foundation

This directory contains the philosophical and theoretical foundation behind the LRSI Runtime Core.

The runtime code is not intended to be understood only as a technical control system. It is grounded in a broader framework around:

- open solution spaces;
- admissibility before optimization;
- HOLD as a valid and necessary control state;
- non-compensable safety boundaries;
- human agency, dissent, and institutional coupling;
- failure modes of self-transforming systems;
- replay, audit, and interruption as practical expressions of path-preserving development.

## Recommended reading path

1. [`D1.pdf`](D1.pdf) - core theoretical frame: the solution space.
2. [`D2.pdf`](D2.pdf) - admissibility: path integrity, irreversibility, externalization.
3. [`D3.pdf`](D3.pdf) - operational examination and gate logic.
4. [`D3a.pdf`](D3a.pdf) - operational deep layer and HOLD principle.
5. [`D4.pdf`](D4.pdf) and [`D4a.pdf`](D4a.pdf) - human/system coupling and agency preservation.
6. [`D6.pdf`](D6.pdf) - critical counter-examination and systematic failure modes.
7. [`D5.pdf`](D5.pdf) - real-world fields of application.
8. [`D7.pdf`](D7.pdf) - open extrapolation and future feedback loops.
9. [`D8.pdf`](D8.pdf) - scientific source basis.

## How this connects to the code

| Foundation concept | Runtime expression |
|---|---|
| Path integrity | Event-sourced replay, non-acceptance of blocked states, phase audit |
| Irreversibility reservation | HOLD / STOP / REJECT states before unsafe continuation |
| Non-externalization | Auditability, evidence binding, explicit decision traces |
| HOLD as clarification | `HOLD` is treated as a real operational state, not as a failure |
| Human agency | Human review, evidence bundles, and review binding |
| Critical counter-examination | Adversarial phases, property tests, integration tests, invariants |
| Self-optimization risk | PreProposal kill-switch, DGM pre-check respect for blocked state |
| Reality coupling | replay, validation, structured diagnostics, anti-proxy safeguards |

## Document map

| File | Layer | Function |
|---|---|---|
| [`D1.pdf`](D1.pdf) | Core layer | Defines the smallest theoretical context: open solution space, preservation/opening, reality coupling, path dependence |
| [`D2.pdf`](D2.pdf) | Normative layer | Defines minimal non-compensable admissibility conditions |
| [`D3.pdf`](D3.pdf) | Operational layer | Translates admissibility into verifiable approximation and gate logic |
| [`D3a.pdf`](D3a.pdf) | Operational deep layer | Adds limitation, reversible steering, and HOLD under real complexity |
| [`D4.pdf`](D4.pdf) | Coupling layer | Human and institutional coupling conditions |
| [`D4a.pdf`](D4a.pdf) | Operational coupling | Makes human-system coupling workable under pressure |
| [`D5.pdf`](D5.pdf) | Unfolding/application layer | Shows structural transferability to real systems |
| [`D6.pdf`](D6.pdf) | Critical layer | Tests the framework against failure, maldevelopment, and self-optimization risk |
| [`D7.pdf`](D7.pdf) | Extrapolation layer | Open extensions and hypotheses, not part of the secured core |
| [`D8.pdf`](D8.pdf) | Source layer | Scientific source basis for the framework |

## Development note

Contributions are explicitly welcome. The philosophical foundation is not meant to close the project. It is meant to make the project more understandable, criticizable, and developable.

Good contributions include:

- clearer diagrams connecting D1-D8 to runtime concepts;
- tests that operationalize a philosophical claim;
- critical documentation that identifies where the runtime does not yet satisfy its own foundation;
- better links between `INVARIANTS.md`, `SECURITY_MODEL.md`, and the D-documents;
- careful refactoring that improves auditability and explainability without weakening safety boundaries.
