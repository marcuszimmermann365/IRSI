# Production-Near Runtime Guide

## Recommended runtime mode

Use explicit paths. Do not rely on working-directory defaults in long-running services.

```python
from runner import main

records = main(
    iterations=1,
    storage_path="/var/lib/lrsi/audit/run_log.json",
    memory_path="/var/lib/lrsi/state/memory_store.json",
    simulation_mode=False,
    return_records=True,
)
```

## Environment variables

| Variable | Purpose |
|---|---|
| `AUDIT_BACKEND=json` | Development materialized JSON backend. |
| `AUDIT_BACKEND=append-only` | Local JSONL append-only backend plus optional materialized JSON. |
| `AUDIT_HMAC_KEY` | Optional local HMAC signature key for audit record hashes. |
| `LLM_MODE=mock|fixture|live` | LLM backend selection. |
| `LLM_FIXTURE_PATH` | Fixture file for deterministic LLM responses. |
| `LRSI_VERBOSE=1` | Human-readable runtime logs. |

## Runtime invariant

The runtime must treat `HOLD`, `STOP`, and `RED` as non-success states. A successful process exit does not imply candidate acceptance; acceptance is only represented by the persisted audit record.

## Deployment boundary

V11.0 can be used as a production-near runtime skeleton. Before production use, bind the following to real infrastructure:

1. human-review adapter
2. reviewer identity
3. external audit sink
4. LLM credentials and retry policy
5. observability/alerting
6. calibrated threshold registry
