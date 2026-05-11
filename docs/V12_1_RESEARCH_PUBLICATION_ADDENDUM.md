# V12.1 — Research Publication Addendum

This addendum documents the publication-oriented additions made after the V12.1
payload-hardening update.

## Added documentation

- `docs/RESEARCH_POSITIONING.md`
- `docs/THREAT_MODEL.md`
- `docs/SAFETY_INVARIANTS.md`
- `docs/RED_TEAM_BENCHMARKS.md`
- `docs/PUBLICATION_NOTES.md`

## Added benchmark scaffold

- `benchmarks/README.md`
- `benchmarks/scenarios/`
- `benchmarks/expected_decisions/`
- `benchmarks/replay_checks/`

## Intent

These documents support scientific and security-oriented review by clarifying:

- what the project claims and does not claim;
- which assets and trust boundaries matter;
- which safety invariants future development should preserve;
- which red-team scenarios should be used to evaluate regressions;
- how the project should be positioned publicly.

The code remains a research-oriented runtime prototype, not a certified
production safety system.
