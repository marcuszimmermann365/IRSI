# LRSI Runtime Core v13.3.0

## Project description and status

**LRSI Runtime Core** is a research-oriented, event-sourced AI safety runtime for studying how an AI-adjacent system can decide whether it should continue, pause, or stop.

The core question is:

> How does a system recognize, record, and enforce that it must not continue?

Version **13.3.0** is the current release-candidate state of the project. It includes a hardened self-modification boundary, central security invariants, a unified security error hierarchy, structured security logs, replayable event-sourced audit trails, and property-based security tests.

This project is **not** a complete AI alignment solution and is **not** a certified production safety system. It is a professional research runtime and security-review substrate for exploring interruptibility, auditability, human review binding, replayable decisions, and controlled self-modification.


## Development is explicitly welcome

**LRSI is intended to be developed further. Contributions, criticism, tests, diagrams, documentation improvements, and careful refactorings are highly welcome.**

The project now contains two entry paths:

1. **Technical entry path** - start with [`README.md`](README.md), [`INVARIANTS.md`](INVARIANTS.md), [`SECURITY_MODEL.md`](SECURITY_MODEL.md), [`OPERATIONS.md`](OPERATIONS.md), and [`docs/good-first-issues.md`](docs/good-first-issues.md).
2. **Philosophical foundation path** - start with [`docs/philosophical-foundation/README.md`](docs/philosophical-foundation/README.md), then read [`D1.pdf`](docs/philosophical-foundation/D1.pdf), [`D2.pdf`](docs/philosophical-foundation/D2.pdf), [`D3a.pdf`](docs/philosophical-foundation/D3a.pdf), and [`D6.pdf`](docs/philosophical-foundation/D6.pdf).

Good first contributions are listed in [`docs/good-first-issues.md`](docs/good-first-issues.md). The contribution process is described in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Quickstart

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install the project with development dependencies

```bash
python -m pip install -e ".[dev]"
```

### 3. Run a first local runtime sample

```bash
python runner.py --iterations 3 --storage-path run_log.json --memory-path memory_store.json
```

This creates the main runtime artifacts:

```text
run_log.json
run_log.json.events.jsonl
run_log.json.events.jsonl.cursor.json
memory_store.json
```

`run_log.json` is a materialized compatibility view. The canonical audit source is the append-only event stream `run_log.json.events.jsonl`.

### 4. Verify tests

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

## Features and security highlights

LRSI v13.3.0 includes:

- **STOP / HOLD / GO control** for runtime decisions.
- **Hard pre-proposal kill-switch** for RED self-modification attempts.
- **Central safety invariants** in `invariants.py`.
- **Unified security error hierarchy** in `security_errors.py`.
- **Event-sourced canonical audit trail** using append-only JSONL.
- **Hash-chain verification** with sequence numbers, `previous_event_hash`, and `event_hash`.
- **Committed event references** in materialized records.
- **Replayable decisions** from the canonical event stream.
- **Human-review and evidence-bundle support**.
- **WORM / external audit sink hooks** for production-like audit persistence.
- **Payload-bounded diagnostics** to prevent recursive audit growth.
- **Structured security logs** for critical security decisions.
- **Property-based security tests** using Hypothesis.
- **Philosophical foundation documents** in `docs/philosophical-foundation/`.
- **Fail-closed self-modification boundary** around mutation, pre-proposal review, DGM pre-check, and final gate behavior.

## Architecture overview

At a high level, LRSI is built around a phase-based runtime pipeline:

```text
Review Mode
  -> Mutation
  -> PreProposalAdversarialPhase
  -> DGMPrecheckPhase
  -> Evaluation
  -> Council
  -> Hold Logic
  -> Human Review
  -> Erosion & Human Coupling
  -> Attractor Analysis
  -> Adversarial Phase
  -> DGMPostcheckPhase
  -> Final Gate
  -> Apply or Reject Candidate
  -> Memory Consolidation
  -> Post-decision Accounting
  -> Observability
  -> Persistence
```

The most security-critical segment is the **Self-Modification Boundary**:

```text
Mutation
  -> PreProposalAdversarialPhase
  -> DGMPrecheckPhase
  -> downstream governance
  -> Final Gate
  -> Persistence
```

Every decision-relevant phase can emit a `phase.result` event. These events are committed to the append-only event stream and later used for projection, replay, verification, and audit.

Key architectural files:

- `pipeline/self_modification_phases.py` — self-modification boundary phases.
- `pipeline/phase_runtime.py` — phase result and execution contracts.
- `eventsourcing.py` — append-only event store, event verification, projection, replay.
- `storage.py` — materialized records and canonical event-store integration.
- `invariants.py` — central security invariants.
- `security_errors.py` — unified security exception hierarchy.

See `ARCHITECTURE.md` for more detail.

## Security model

LRSI v13.3.0 follows a fail-closed security model for self-modification and critical runtime decisions.

A RED result in `PreProposalAdversarialPhase` is terminal:

```text
decision: RED
terminal: true
mutation_blocked: true
block_reason: <reason>
```

A blocked mutation must not pass DGM pre-check, must not be accepted by the final gate, and must not alter the effective policy.

The current invariant set prevents:

- RED pre-proposal acceptance.
- Blocked mutation continuation through DGM or final gate.
- Mutation without pre-proposal adversarial coverage.
- HOLD-state mutation application.
- Council RED being softened into GO/HOLD/ACCEPT.
- Terminal security events carrying GO/ACCEPT semantics.
- Blocked records changing the effective policy.
- Materialized records whose event references do not cover phase audit.
- Event-chain inconsistency after blocked states.

Security-relevant failures use `LRSISecurityError` or a subclass. `InvariantViolation` inherits from `LRSISecurityError`.

See:

- `INVARIANTS.md`
- `SECURITY_MODEL.md`
- `SECURITY_CHANGES_v13.0.md`

## Installation and dependencies

### Python version

The project requires Python **3.10+**.

### Runtime dependency

The core runtime dependency is:

```text
cryptography>=42
```

### Development dependencies

Development dependencies are installed with:

```bash
python -m pip install -e ".[dev]"
```

The dev dependency set includes:

- `pytest`
- `hypothesis`
- `ruff`
- `mypy`
- `bandit`

### Optional live dependency

For live LLM integration:

```bash
python -m pip install -e ".[live]"
```

## Development

### Run the main test suite

```bash
python -m pytest -q -rs
```

### Run property-based security tests

```bash
python -m pytest tests/test_v122_property_based_security.py -q
```

v13.3.0 includes at least 10 property-based tests; the current suite contains 14 property-based tests covering event-chain load, tamper attempts, logging integrity, multi-stage blockades, simultaneous invariant violations, RED/YELLOW/GREEN boundary behavior, HOLD behavior, Council RED behavior, and DGM blocked-state handling.

### Run phase-event coverage check

```bash
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

### Run optional static checks

```bash
ruff check .
mypy .
bandit -r .
```

These tools are part of the development dependencies but may need environment-specific configuration for CI.

### CI recommendation

A minimal CI workflow should run:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
python -m pytest tests/test_v122_property_based_security.py -q
```

For security-sensitive pull requests, CI should additionally fail if:

- the event chain cannot be verified;
- RED pre-proposal states can become GO/ACCEPT;
- HOLD states apply mutations;
- Council RED is softened into HOLD/GO/ACCEPT;
- event refs do not cover phase audit;
- a blocked mutation changes effective policy.

## Security logging

Security logs are quiet by default through `NullHandler`.

To observe structured security logs, attach handlers to:

```text
lrsi.security.invariants
lrsi.security.eventsourcing
lrsi.security.storage
```

v13.3.0 defines symbolic logging levels:

```text
SECURITY = 35
AUDIT = 25
```

Example:

```python
import logging

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

for name in [
    "lrsi.security.invariants",
    "lrsi.security.eventsourcing",
    "lrsi.security.storage",
]:
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
```

Security log entries are JSON-like strings and may include:

- `trace_id`
- `iteration`
- `decision`
- `phase`
- `reason`
- `event_hash`
- `previous_event_hash`
- `record_hash`
- `block_reason`

## Known limitations

LRSI v13.3.0 is a hardened research runtime, but it has important limitations:

- It is **not** a formal proof of AI safety.
- It is **not** a certified production safety system.
- It does **not** secure model weights.
- It does **not** solve training-time alignment.
- It does **not** provide a full identity and access-management system.
- Reviewer identity and authorization must be supplied by deployment infrastructure.
- WORM/external sink guarantees depend on real infrastructure configuration.
- LLM behavior and adversarial diagnostics still require empirical calibration.
- The invariant set is an engineering control layer, not a mathematical guarantee.
- Production-like operation requires external key management, protected signing keys, and independent audit infrastructure.

## Important documents

Start here:

- `INVARIANTS.md` — central security invariants.
- `SECURITY_MODEL.md` — current security model and fail-closed assumptions.
- `OPERATIONS.md` — how to run, test, log, and operate the runtime.
- `ARCHITECTURE.md` — architecture and Self-Modification Boundary.
- `SECURITY_CHANGES_v13.0.md` — final security-hardening summary.
- `CHANGELOG.md` — release history from v12.0/v12.1 to v13.0.
- `CONTRIBUTING.md` — contribution guidance.
- `docs/good-first-issues.md` — ready-to-copy starter issues.
- `docs/philosophical-foundation/README.md` — entry point into the philosophical foundation.
- `docs/philosophical-foundation/INDEX.md` — compact D-series map.
- `docs/philosophical-foundation/D1.pdf` — core solution-space theory.
- `docs/philosophical-foundation/D2.pdf` — admissibility and non-compensable boundaries.
- `docs/philosophical-foundation/D3a.pdf` — HOLD, limitation, and reversible steering.
- `docs/philosophical-foundation/D6.pdf` — critical counter-examination and failure modes.
- `LICENSE` — Apache License 2.0.

Additional research and publication documents:

- `docs/RESEARCH_POSITIONING.md`
- `docs/THREAT_MODEL.md`
- `docs/SAFETY_INVARIANTS.md`
- `docs/RED_TEAM_BENCHMARKS.md`
- `docs/PUBLICATION_NOTES.md`

## License

Apache License 2.0. See `LICENSE`.
