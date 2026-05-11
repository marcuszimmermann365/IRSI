"""V11.2 event/phase runtime contract tests."""

import os
import tempfile

import runner
from pipeline.phase_runtime import PhaseResult
from pipeline.phase_services import CouncilPhase, CouncilPhaseInput
from storage import verify_hash_chain
from version import SCHEMA_VERSION


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def main():
    check("schema_version_v112", SCHEMA_VERSION in {"11.2", "11.3", "11.4", "11.5", "11.6", "12.0"})
    result = PhaseResult(phase="x", decision="GREEN", patch={"a": 1})
    check("phase_result_audit_entry", result.audit_entry(iteration=1)["phase"] == "x")
    phase = CouncilPhase()
    check("council_phase_input_type", phase.input_type is CouncilPhaseInput)
    check("council_phase_requires_explicit_keys", "parent_metrics" in phase.required_keys and "candidate" in phase.required_keys)
    with tempfile.TemporaryDirectory() as tmp:
        records = runner.main(
            iterations=1,
            return_records=True,
            storage_path=os.path.join(tmp, "run.json"),
            memory_path=os.path.join(tmp, "mem.json"),
        )
        check("runner_returns_one_record", len(records) == 1)
        check("phase_audit_present", len(records[0].get("phase_audit", [])) >= 5)
        check("council_phase_audited", "council_phase" in [e["phase"] for e in records[0]["phase_audit"]])
        ok, errors = verify_hash_chain(records)
        check("hash_chain_valid", ok and not errors)
    print("V11.2 phase runtime checks passed")


if __name__ == "__main__":
    main()
