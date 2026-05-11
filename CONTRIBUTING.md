# Contributing

Thank you for considering contributing to LRSI Runtime Core.

This project is a research-oriented AI safety runtime. Contributions should
preserve the fail-closed self-modification boundary and the event-sourced
audit model.

## Before submitting a change

Run:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

For security-relevant changes, also run:

```bash
python -m pytest tests/test_v122_property_based_security.py -q
```

## Security-sensitive areas

Changes to these files require extra care:

- `invariants.py`
- `security_errors.py`
- `eventsourcing.py`
- `storage.py`
- `pipeline/self_modification_phases.py`
- `pipeline/phase_runtime.py`
- `pipeline/phase_flow.py`

## Rules for new phases

A new decision-relevant phase should define:

- typed input contract;
- typed output or `PhaseResult`;
- bounded diagnostics;
- event emission;
- replay relevance;
- tests;
- relevant invariant coverage.

## Public claims

Do not describe this project as a solved alignment system or certified safety
product. Use restrained language such as:

- research runtime;
- experimental safety control plane;
- event-sourced audit and replay substrate;
- interruptibility and self-modification boundary study.
