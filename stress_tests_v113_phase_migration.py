"""V11.3 safe phase migration contract tests."""

import os
import tempfile

import runner
from pipeline.phase_services import (
    FinalGatePhase,
    HoldLogicPhase,
    HumanReviewPhase,
    PersistencePhase,
    PostRunReporter,
)
from storage import verify_hash_chain
from version import SCHEMA_VERSION


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def main():
    check("schema_version_v113", SCHEMA_VERSION in {"11.3", "11.4", "11.5", "11.6", "12.0"})
    for phase in [HoldLogicPhase(), HumanReviewPhase(), FinalGatePhase(), PersistencePhase(), PostRunReporter()]:
        check(f"{phase.name}_has_required_keys", bool(phase.required_keys))
        check(f"{phase.name}_has_input_type", phase.input_type is not None)
    with tempfile.TemporaryDirectory() as tmp:
        records = runner.main(
            iterations=1,
            return_records=True,
            storage_path=os.path.join(tmp, "run.json"),
            memory_path=os.path.join(tmp, "mem.json"),
        )
        phases = [e["phase"] for e in records[0].get("phase_audit", [])]
        for name in ["council_phase", "hold_logic", "human_review", "final_gate", "persist_iteration_record"]:
            check(f"{name}_audited", name in phases)
        ok, errors = verify_hash_chain(records)
        check("hash_chain_valid", ok and not errors)
    print("V11.3 safe phase migration checks passed")


if __name__ == "__main__":
    main()
