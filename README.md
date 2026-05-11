# LRSI Runtime Core v13.0.0

**LRSI Runtime Core** is a research-oriented, event-sourced AI safety runtime
for studying interruptibility, auditability, human review binding, replayable
decisions, payload-bounded diagnostics, and self-modification boundaries.

The central question is:

> How does a system recognize, record, and enforce that it must not continue?

This repository is not a complete AI alignment solution and is not a certified
production safety system. It is a professional research runtime and security
review substrate.

## Core features

- STOP / HOLD / GO runtime control
- hard pre-proposal kill-switch for RED self-modification attempts
- central safety invariants in `invariants.py`
- unified `LRSISecurityError` hierarchy in `security_errors.py`
- event-sourced canonical audit trail
- append-only JSONL event stream with hash-chain verification
- committed event references in materialized records
- replayable final decisions
- human-review and evidence-bundle support
- WORM / external audit sink hooks
- payload-bounded diagnostics
- structured security logs
- property-based security tests with Hypothesis

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```bash
python runner.py --iterations 3 --storage-path run_log.json --memory-path memory_store.json
```

Quiet mode:

```bash
python runner.py --iterations 3 --quiet
```

Verbose mode:

```bash
python runner.py --iterations 3 --verbose
```

## Test

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

Property-based tests:

```bash
python -m pytest tests/test_v122_property_based_security.py -q
```

## Audit and replay

A normal run writes:

```text
run_log.json
run_log.json.events.jsonl
run_log.json.events.jsonl.cursor.json
memory_store.json
```

`run_log.json` is a materialized compatibility view. The canonical audit
source is the append-only event stream.

```python
from storage import Storage

storage = Storage("run_log.json")
ok, errors = storage.verify_event_chain()
projection = storage.project_events()
replay = storage.replay_decisions()
```

## Security model

v13.0.0 enforces a fail-closed self-modification boundary:

```text
Mutation
  -> PreProposalAdversarialPhase
  -> DGMPrecheckPhase
  -> downstream governance
  -> Final Gate
  -> Persistence
```

A RED pre-proposal result is terminal:

```text
decision: RED
terminal: true
mutation_blocked: true
block_reason: <reason>
```

Central invariants prevent:

- RED pre-proposal acceptance;
- blocked mutation continuation through DGM or final gate;
- mutation without pre-proposal adversarial coverage;
- HOLD-state mutation application;
- Council RED being softened into GO/HOLD/ACCEPT;
- terminal events with GO/ACCEPT semantics;
- blocked records changing the effective policy;
- phase audit records lacking committed event references.

See:

- `SECURITY_MODEL.md`
- `INVARIANTS.md`
- `SECURITY_CHANGES_v13.0.md`
- `ARCHITECTURE.md`
- `OPERATIONS.md`

## Structured security logs

Security logs are quiet by default. Attach handlers explicitly to:

- `lrsi.security.invariants`
- `lrsi.security.eventsourcing`
- `lrsi.security.storage`

v13.0.0 defines symbolic logging levels:

- `SECURITY = 35`
- `AUDIT = 25`

## Production-like operation

Production-like operation should require:

- asymmetric event signing;
- independently governed external/WORM audit sink;
- protected signing keys;
- event-chain verification;
- replay checks;
- reviewer identity and authorization outside this runtime.

See `OPERATIONS.md`.

## Known limitations

- This is a research runtime, not a certified production safety system.
- It does not secure model weights or training-time alignment.
- Reviewer identity and authorization must be provided by deployment infrastructure.
- WORM/external sink guarantees depend on actual infrastructure.
- Invariants are engineering constraints and tests, not a formal proof of safety.
- LLM behavior and adversarial diagnostics still require empirical calibration.

## License

Apache License 2.0. See `LICENSE`.
