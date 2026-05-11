"""V11.4 safety diagnostics migration contract tests."""

import os
import tempfile

import runner
from pipeline.phase_services import AdversarialPhase, AttractorPhase
from storage import verify_hash_chain
from version import SCHEMA_VERSION


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def main():
    check("schema_version_v114", SCHEMA_VERSION in {"11.4", "11.5", "11.6", "12.0"})
    check("attractor_phase_has_input_contract", AttractorPhase().required_keys and AttractorPhase().input_type)
    check("adversarial_phase_has_input_contract", AdversarialPhase().required_keys and AdversarialPhase().input_type)
    with tempfile.TemporaryDirectory() as tmp:
        records = runner.main(
            iterations=1,
            return_records=True,
            storage_path=os.path.join(tmp, "run.json"),
            memory_path=os.path.join(tmp, "mem.json"),
        )
        record = records[0]
        phases = [e["phase"] for e in record.get("phase_audit", [])]
        check("attractor_phase_audited", "attractor_phase" in phases)
        check("adversarial_phase_audited", "adversarial_phase" in phases)
        check("attractor_nested_recorded", bool(record.get("attractor_diagnostics_v11_4")))
        adv = record.get("adversarial_diagnostics_v11_4", {})
        for key in ["drel", "a3", "agency", "a4", "pareto", "sham_resonance", "carrier_erosion", "complexity", "auxiliary"]:
            check(f"adversarial_{key}_nested", key in adv)
        ok, errors = verify_hash_chain(records)
        check("hash_chain_valid", ok and not errors)
    print("V11.4 safety diagnostics migration checks passed")


if __name__ == "__main__":
    main()
