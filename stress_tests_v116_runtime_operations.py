"""Executable V11.6 runtime operations contract suite."""

import tempfile
from pathlib import Path

import runner
from storage import verify_hash_chain


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def phase_names(record):
    return [entry.get("phase") for entry in record.get("phase_audit", [])]


def main():
    with tempfile.TemporaryDirectory() as td:
        records = runner.main(
            iterations=2,
            storage_path=str(Path(td) / "run_log.json"),
            memory_path=str(Path(td) / "memory_store.json"),
            return_records=True,
        )
        ok, errors = verify_hash_chain(records)
        check(ok, f"hash chain valid: {errors}")
        first = records[0]
        check(first.get("trace_id", "").startswith("lrsi-"), "trace_id propagated to record")
        phases = phase_names(first)
        for expected in ("evaluation_phase", "memory_consolidation_phase", "observability_phase"):
            check(expected in phases, f"{expected} audited")
        runtime = first.get("runtime_operations_v11_6", {})
        for key in ("evaluation", "memory_consolidation", "observability", "runtime_events"):
            check(key in runtime, f"runtime block contains {key}")
        check(runtime["observability"].get("trace_id") == first["trace_id"], "observability uses record trace_id")
        check(runtime["runtime_events"][0]["event_type"] == "iteration_completed", "structured runtime event emitted")
        for entry in first.get("phase_audit", []):
            check(entry.get("trace_id") == first["trace_id"], f"phase {entry.get('phase')} has trace_id")
    print("\nV11.6 runtime operations suite: all checks passed")


if __name__ == "__main__":
    main()
