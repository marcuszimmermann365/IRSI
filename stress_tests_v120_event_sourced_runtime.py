"""Executable V12.0 event-sourced runtime contract tests."""

import json
import os
import tempfile

from eventsourcing import RuntimeEvent, replay_decisions, verify_event_chain
from runner import main as run_pipeline
from storage import Storage


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_runner_events_replay():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_log.json")
        mem = os.path.join(d, "memory.json")
        records = run_pipeline(iterations=1, storage_path=path, memory_path=mem, return_records=True, verbose=False)
        events = [json.loads(line) for line in open(path + ".events.jsonl", encoding="utf-8") if line.strip()]
        ok, errors = verify_event_chain(events)
        check(ok, f"event chain invalid: {errors}")
        replay = replay_decisions(events)
        check(replay["decisions"][0]["final_decision"] == records[0]["final_decision"], "replay decision mismatch")


def test_storage_event_store_available():
    with tempfile.TemporaryDirectory() as d:
        storage = Storage(os.path.join(d, "run_log.json"))
        storage.log_iteration({
            "iteration": 0,
            "final_decision": "HOLD",
            "accepted": False,
            "events_v12": [RuntimeEvent(event_type="phase.result", phase="unit", iteration=0, payload={"phase_result": {"decision": "HOLD"}}).to_dict()],
        })
        check(storage.load_events(), "no events written")
        ok, errors = storage.verify_event_chain()
        check(ok, f"storage event chain invalid: {errors}")


def main():
    tests = [test_runner_events_replay, test_storage_event_store_available]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"V12.0 event-sourced runtime stress tests: {passed} passed, 0 failed")


if __name__ == "__main__":
    main()
