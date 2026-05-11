import json
import subprocess
import sys
from pathlib import Path

import pytest

import runner
from eventsourcing import (
    AppendOnlyEventStore,
    EventStoreCorruptionError,
    RuntimeEvent,
    project_events,
    replay_decisions,
    validate_phase_audit_event_coverage,
    verify_event_chain,
)


class FailingSink:
    sink_name = "failing-test-sink"

    def write_once(self, event_id: str, payload: dict) -> dict:  # noqa: ARG002
        raise OSError("simulated external sink outage")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_terminal_reject_path_has_phase_result_event_coverage_and_mutant_fails(tmp_path):
    records = runner.main(
        iterations=3,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
        verbose=False,
    )
    events = _read_jsonl(tmp_path / "run_log.json.events.jsonl")

    ok, errors = validate_phase_audit_event_coverage(records, events)
    assert ok, errors

    reject = records[2]
    assert reject["gate_reason"] in {
        "dgm_pre:immutable_core_violation",
        "preproposal:preproposal_attack_red",
    }
    terminal_phase_names = [entry["phase"] for entry in reject["phase_audit"]]
    expected_terminal_phase = (
        "preproposal_adversarial_phase"
        if reject["gate_reason"].startswith("preproposal:")
        else "dgm_precheck_phase"
    )
    expected_terminal_names = [
        "review_mode",
        "mutation_phase",
        "preproposal_adversarial_phase",
    ]
    if expected_terminal_phase == "dgm_precheck_phase":
        expected_terminal_names.append("dgm_precheck_phase")
    assert terminal_phase_names == expected_terminal_names

    # Mutation-style regression: remove only the terminal phase.result event and
    # ensure the invariant detects that the materialized phase_audit view is no
    # longer replayable from the canonical event stream.
    mutant_events = [
        event
        for event in events
        if not (
            event.get("event_type") == "phase.result"
            and event.get("iteration") == 2
            and event.get("phase") == expected_terminal_phase
        )
    ]
    ok, errors = validate_phase_audit_event_coverage(records, mutant_events)
    assert not ok
    assert any(expected_terminal_phase in error for error in errors)


def test_replay_can_use_only_phase_result_events_without_materialized_records():
    phase_only_events = [
        RuntimeEvent(
            event_type="phase.result",
            phase="review_mode",
            iteration=0,
            payload={
                "phase_result": {
                    "iteration": 0,
                    "phase": "review_mode",
                    "decision": "CHECKED",
                    "reason": "not_review",
                    "terminal": False,
                }
            },
        ).to_dict(),
        RuntimeEvent(
            event_type="phase.result",
            phase="dgm_precheck_phase",
            iteration=0,
            payload={
                "phase_result": {
                    "iteration": 0,
                    "phase": "dgm_precheck_phase",
                    "decision": "REJECT",
                    "reason": "immutable_core_violation",
                    "terminal": True,
                }
            },
        ).to_dict(),
    ]

    projection = project_events(phase_only_events)
    replay = replay_decisions(phase_only_events)

    assert projection["final_records"] == []
    assert replay["decision_count"] == 1
    assert replay["decisions"][0] == {
        "iteration": 0,
        "final_decision": "REJECT",
        "accepted": False,
        "phase_count": 2,
        "record_hash": None,
    }


def test_corrupt_jsonl_line_is_explicitly_rejected_on_restart(tmp_path):
    path = tmp_path / "events.jsonl"
    store = AppendOnlyEventStore(str(path))
    store.append(RuntimeEvent(event_type="phase.result", phase="unit", payload={"n": 1}))
    with path.open("a", encoding="utf-8") as f:
        f.write('{"event_type": "corrupt", bad-json}\n')

    with pytest.raises(EventStoreCorruptionError, match="corrupt JSONL event at line 2"):
        AppendOnlyEventStore(str(path))


def test_external_sink_failure_does_not_advance_local_event_stream(tmp_path):
    path = tmp_path / "events.jsonl"
    store = AppendOnlyEventStore(str(path), external_sink=FailingSink())

    with pytest.raises(OSError, match="simulated external sink outage"):
        store.append(RuntimeEvent(event_type="phase.result", phase="unit", payload={"n": 1}))

    assert path.read_text(encoding="utf-8") == ""
    assert _read_jsonl(path) == []

    healthy = AppendOnlyEventStore(str(path))
    first = healthy.append(RuntimeEvent(event_type="phase.result", phase="unit", payload={"n": 2}))
    assert first["sequence"] == 0
    ok, errors = healthy.verify()
    assert ok, errors


def test_restart_after_trailing_partial_write_repairs_tail_and_continues_hash_chain(tmp_path):
    path = tmp_path / "events.jsonl"
    store = AppendOnlyEventStore(str(path))
    first = store.append(RuntimeEvent(event_type="phase.result", phase="one", payload={"n": 1}))
    with path.open("ab") as f:
        f.write(b'{"event_type":"partial"')

    restarted = AppendOnlyEventStore(str(path))
    assert restarted.load() == [first]
    second = restarted.append(RuntimeEvent(event_type="phase.result", phase="two", payload={"n": 2}))

    assert second["sequence"] == 1
    assert second["previous_event_hash"] == first["event_hash"]
    ok, errors = verify_event_chain(restarted.load())
    assert ok, errors


def test_ci_phase_event_coverage_script_accepts_sample_and_rejects_mutant(tmp_path):
    sample = subprocess.run(
        [
            sys.executable,
            "scripts/check_phase_event_coverage.py",
            "--run-sample",
            "--iterations",
            "3",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert sample.returncode == 0, sample.stderr + sample.stdout
    assert "phase_audit/phase.result coverage ok" in sample.stdout

    records = runner.main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
        verbose=False,
    )
    events = _read_jsonl(tmp_path / "run_log.json.events.jsonl")
    # Deliberately remove all phase.result events to simulate a coverage mutant.
    mutant_path = tmp_path / "mutant.events.jsonl"
    mutant_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in events if e.get("event_type") != "phase.result") + "\n",
        encoding="utf-8",
    )
    (tmp_path / "run_log.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    mutant = subprocess.run(
        [
            sys.executable,
            "scripts/check_phase_event_coverage.py",
            "--log",
            str(tmp_path / "run_log.json"),
            "--events",
            str(mutant_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert mutant.returncode == 1
    assert "missing phase.result" in mutant.stderr
