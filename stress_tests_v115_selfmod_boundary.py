"""Executable V11.5 self-modification boundary contract suite."""

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
            iterations=3,
            storage_path=str(Path(td) / "run_log.json"),
            memory_path=str(Path(td) / "memory_store.json"),
            return_records=True,
        )
        ok, errors = verify_hash_chain(records)
        check(ok, f"hash chain valid: {errors}")
        check(len(records) == 3, "three iteration records returned")
        first = records[0]
        phases = phase_names(first)
        for expected in ("mutation_phase", "preproposal_adversarial_phase", "dgm_precheck_phase", "dgm_postcheck_phase"):
            check(expected in phases, f"{expected} audited in normal iteration")
        boundary = first.get("self_modification_boundary_v11_5", {})
        check(set(boundary) == {"mutation", "preproposal", "dgm_precheck", "dgm_postcheck"}, "boundary block has all four self-modification sections")
        check(boundary["dgm_precheck"]["allowed"] is True, "allowed DGM precheck recorded")
        check(boundary["dgm_postcheck"]["diagnostics"]["proposal_id"] == boundary["dgm_precheck"]["proposal"]["change_id"], "DGM pre/post proposal identity preserved")
        reject = records[2]
        check(reject["dgm"]["pre_check"]["allowed"] is False, "immutable DGM pre-reject recorded")
        check("dgm_precheck_phase" in phase_names(reject), "terminal DGM reject keeps phase audit")
    print("\nV11.5 self-modification boundary suite: all checks passed")


if __name__ == "__main__":
    main()
