# Benchmarks

This directory is a scaffold for research and red-team benchmarks.

Start with the scenario definitions in:

- `docs/RED_TEAM_BENCHMARKS.md`
- `benchmarks/scenarios/`

A future benchmark runner should execute each scenario, verify the committed
event chain, replay the final decision, inspect payload sizes, and compare the
runtime outcome with the expected decision semantics.
