import json
from pathlib import Path

from runner import main


def test_runtime_audit_payloads_remain_bounded_for_multi_iteration_runs(tmp_path):
    run_log = tmp_path / "run_log.json"
    memory = tmp_path / "memory.json"

    main(
        iterations=5,
        storage_path=str(run_log),
        memory_path=str(memory),
        return_records=True,
        verbose=False,
    )

    events_path = Path(str(run_log) + ".events.jsonl")
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    max_event_bytes = max(len(json.dumps(event, sort_keys=True).encode("utf-8")) for event in events)

    assert run_log.stat().st_size < 2_000_000
    assert events_path.stat().st_size < 2_000_000
    assert max_event_bytes < 250_000

    records = json.loads(run_log.read_text())
    assert records[0]["events_v12"]
    assert "payload" not in records[0]["events_v12"][0]
    assert records[0]["events_v12"][0]["sequence"] == 0
    assert records[0]["event_sourcing_v12_0"]["materialized_events_shape"] == "committed_event_refs"
