# Operations Guide — LRSI Runtime Core v12.2.0

## Purpose

This guide describes how to run, test, observe, and prepare the LRSI runtime
for production-like operation.

LRSI is still an experimental research runtime. It is not a certified
production safety system.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The development dependencies include:

- `pytest`;
- `hypothesis`;
- `ruff`;
- `mypy`;
- `bandit`.

## Run the runtime locally

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

Return records from Python:

```python
import runner

records = runner.main(
    iterations=3,
    storage_path="run_log.json",
    memory_path="memory_store.json",
    return_records=True,
    verbose=False,
)
```

## Run tests

Minimum validation:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
```

Property-based security tests:

```bash
python -m pytest tests/test_v122_property_based_security.py -q
```

Optional static checks:

```bash
ruff check .
mypy .
bandit -r .
```

## Audit artifacts

Typical runtime artifacts:

- `run_log.json` — materialized compatibility view;
- `run_log.json.events.jsonl` — canonical event stream;
- `run_log.json.events.jsonl.cursor.json` — append cursor sidecar;
- `memory_store.json` — memory store.

The canonical audit source is the append-only event stream, not
`run_log.json`.

## Verify event chain

From Python:

```python
from storage import Storage

storage = Storage("run_log.json")
ok, errors = storage.verify_event_chain()
assert ok, errors
```

## Replay decisions

```python
from storage import Storage

storage = Storage("run_log.json")
replay = storage.replay_decisions()
print(replay)
```

## Security logging

v12.2.0 provides structured security logs under:

- `lrsi.security.invariants`;
- `lrsi.security.eventsourcing`;
- `lrsi.security.storage`.

The loggers are quiet-by-default. Attach handlers explicitly:

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

Security-relevant logs are JSON-like strings containing fields such as
`trace_id`, `iteration`, `decision`, `phase`, `event_hash`, `record_hash`,
and `block_reason`.

## Production-like mode

Production-like operation should fail closed without signed and externalized
audit controls.

Recommended environment shape:

```bash
export LRSI_PRODUCTION_MODE=1
export AUDIT_SIGNING_MODE=ed25519
# Configure Ed25519 key material outside the repository.
# Configure external/WORM sink outside the repository.
```

Requirements for production-like deployment:

1. asymmetric event signing;
2. independent external/WORM audit sink;
3. protected signing keys;
4. regular event-chain verification;
5. replay checks in CI/CD;
6. explicit reviewer identity and authorization outside this runtime;
7. monitoring of pending external sink journals.

## Operational safety checks

Before publishing or deploying a new build:

```bash
python -m compileall -q .
python -m pytest -q -rs
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
python -m pytest tests/test_v122_property_based_security.py -q
```

Check that:

- RED pre-proposal states are terminal;
- blocked mutations cannot become GO/ACCEPT;
- HOLD states do not apply mutations;
- Council RED leads to STOP/REJECT/ROLLBACK semantics;
- event-chain tampering is detected;
- replay does not depend on `run_log.json`.

## Troubleshooting

### Tests fail due to missing Hypothesis

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Or install directly:

```bash
python -m pip install hypothesis
```

### Event chain verification fails

Treat this as a security incident unless you are intentionally testing
tampering. Preserve the event stream and materialized view for inspection.

### Production mode refuses to start

Check signing mode, signing adapter, external sink configuration, and WORM
setup. Production mode is designed to fail closed when audit controls are
incomplete.

### Logs are silent

This is expected by default. Attach explicit handlers to the
`lrsi.security.*` loggers.


## v13.0.0 logging configuration

Security logs remain quiet by default. For production-like runs, attach explicit handlers to `lrsi.security.*` and route SECURITY level events to durable operational telemetry.
