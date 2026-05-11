"""
V9 Integration Smoke Tests
============================
End-to-end test of runner.main() — the test that would have caught
the `child` NameError that ChatGPT correctly identified.

V7 lesson: lokale Kohärenz ersetzt keine Systemkohärenz.
Unit tests passing != pipeline running.

These tests use temporary storage paths so they don't pollute
run_log.json or memory_store.json.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


def test_smoke_main_completes():
    """SM.1: runner.main() runs end-to-end without exception."""
    print("\n=== SM: Integration Smoke ===")

    # Suppress stdout from main() so test output is clean
    import contextlib
    import io

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")

        try:
            import runner
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                runner.main(
                    iterations=2,
                    storage_path=log_path,
                    memory_path=mem_path,
                    simulation_mode=True,
                )
            check("SM.1 main_completes_2_iterations", True)
        except NameError as e:
            check("SM.1 main_completes_2_iterations", False,
                  f"NameError: {e}")
            return  # Cannot continue if main blew up
        except Exception as e:
            check("SM.1 main_completes_2_iterations", False,
                  f"{type(e).__name__}: {e}")
            return

    # SM.2: produces records when asked
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=3,
                storage_path=log_path,
                memory_path=mem_path,
                simulation_mode=True,
                return_records=True,
            )
        check("SM.2 returns_records",
              isinstance(records, list) and len(records) == 3,
              f"got {type(records).__name__} len={len(records) if records else 0}")

    # SM.3: doesn't write to default paths
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")
        # Capture mtime of any default-named file before
        cwd_log = os.path.join(os.getcwd(), "run_log.json")
        before_mtime = (os.path.getmtime(cwd_log)
                         if os.path.exists(cwd_log) else None)

        import contextlib as ctx2
        import io as io2
        captured = io2.StringIO()
        with ctx2.redirect_stdout(captured):
            runner.main(
                iterations=2,
                storage_path=log_path,
                memory_path=mem_path,
                simulation_mode=True,
            )

        after_mtime = (os.path.getmtime(cwd_log)
                        if os.path.exists(cwd_log) else None)
        # If the file existed before, mtime should be unchanged
        # If it didn't exist before, it shouldn't exist after either
        unpolluted = (before_mtime == after_mtime)
        check("SM.3 default_paths_not_polluted",
              unpolluted,
              f"before={before_mtime} after={after_mtime}")

    # SM.4: temp log was actually written
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")
        captured = io2.StringIO()
        with ctx2.redirect_stdout(captured):
            runner.main(
                iterations=2,
                storage_path=log_path,
                memory_path=mem_path,
                simulation_mode=True,
            )
        check("SM.4 temp_log_written",
              os.path.exists(log_path) and os.path.getsize(log_path) > 0)


def test_v9_modules_in_decision_trace():
    """SM.5-SM.8: V9 stages appear in decision_trace from real run."""
    import contextlib
    import io

    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=3,
                storage_path=log_path,
                memory_path=mem_path,
                simulation_mode=True,
                return_records=True,
            )

    # Collect all decision_trace stages from all records
    all_stages = set()
    for rec in records:
        trace = rec.get("decision_trace", [])
        for entry in trace:
            stage = entry.get("stage", "")
            if stage:
                all_stages.add(stage)

    check("SM.5 v9_sham_resonance_in_trace",
          "v9_sham_resonance" in all_stages,
          f"stages: {sorted(all_stages)[:10]}")
    check("SM.6 v9_carrier_erosion_in_trace",
          "v9_carrier_erosion" in all_stages)
    check("SM.7 v9_complexity_admissibility_in_trace",
          "v9_complexity_admissibility" in all_stages)
    check("SM.8 v9_auxiliary_indicators_in_trace",
          "v9_auxiliary_indicators" in all_stages)

    # SM.9: extended_gate diagnostics carry v9 fields
    found_v9_diag = False
    for rec in records:
        eg = rec.get("extended_gate", {})
        if isinstance(eg, dict):
            diag = eg.get("diagnostics", {})
            if isinstance(diag, dict) and "v9_sham_resonance" in diag:
                found_v9_diag = True
                break
    check("SM.9 v9_diagnostics_in_extended_gate", found_v9_diag)


def test_iteration_zero_safe():
    """SM.10: zero iterations doesn't crash."""
    import contextlib
    import io

    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "run_log.json")
        mem_path = os.path.join(tmpdir, "memory.json")
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                runner.main(
                    iterations=0,
                    storage_path=log_path,
                    memory_path=mem_path,
                    simulation_mode=True,
                )
            check("SM.10 zero_iterations_safe", True)
        except Exception as e:
            check("SM.10 zero_iterations_safe", False, str(e))


# ══════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_smoke_main_completes()
    test_v9_modules_in_decision_trace()
    test_iteration_zero_safe()

    print()
    print("=" * 64)
    print(f"V9 SMOKE TESTS: {len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9-Smoke-Tests bestanden.")
