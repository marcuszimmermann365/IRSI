"""LRSI V11.1 runtime validation stress contracts."""

import tempfile
from pathlib import Path

from audit_sinks import LocalWORMDirectorySink
from calibration import ShadowDecision, ThresholdCalibrationAnalyzer
from review_interface import TwoFactorReviewGate
from runner import main
from semantic_drift import SemanticDriftMonitor
from storage import Storage, verify_hash_chain
from version import SCHEMA_VERSION

passes = 0
fails = 0


def check(name, condition):
    global passes, fails
    if condition:
        print(f"PASS {name}")
        passes += 1
    else:
        print(f"FAIL {name}")
        fails += 1


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    records = main(
        iterations=1,
        storage_path=str(tmp / "run_log.json"),
        memory_path=str(tmp / "memory.json"),
        return_records=True,
    )
    check("schema_version_v111", records[0]["schema_version"] == SCHEMA_VERSION and SCHEMA_VERSION in {"11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0"})
    ok, errors = verify_hash_chain(records)
    check("hash_chain_strict", ok and not errors)
    check("semantic_drift_recorded", "semantic_drift" in records[0])
    check("preproposal_adversarial_recorded", "preproposal_adversarial" in records[0])
    if records[0]["final_decision"] != "GO":
        check("case_file_present_on_hold", records[0].get("evidence_bundle", {}).get("schema") == "lrsi.evidence_bundle.v1")

    storage = Storage(str(tmp / "seal_log.json"))
    storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    seal = storage.seal_sequence(external_sink=LocalWORMDirectorySink(str(tmp / "worm")), sequence_id="stress-seal")
    check("seal_merkle_root_present", len(seal["merkle_root"]) == 64)
    check("seal_externalized", (tmp / "worm" / "stress-seal.json").exists())

monitor = SemanticDriftMonitor(yellow_threshold=0.05)
check("semantic_monitor_green_same", monitor.compare("abc", "abc").decision == "GREEN")
check("semantic_monitor_moves", monitor.compare("abc", "xyz policy override").distance > 0.0)

approvals = [
    TwoFactorReviewGate.simulated_approval("security_auditor", reviewer_id="a").to_dict(),
    TwoFactorReviewGate.simulated_approval("system_operator", reviewer_id="b").to_dict(),
]
check("two_factor_roles", TwoFactorReviewGate().validate(approvals)[0])

summary = ThresholdCalibrationAnalyzer.analyze([
    ShadowDecision("r", 0, "RED", "HOLD", "approve").to_dict(),
    ShadowDecision("r", 1, "GREEN", "GO", "approve", later_outcome="drift").to_dict(),
])
check("shadow_calibration_counts", summary["false_positive_count"] == 1 and summary["false_negative_count"] == 1)

print(f"\nV11.1 stress contracts: {passes} passed, {fails} failed")
if fails:
    raise SystemExit(1)
