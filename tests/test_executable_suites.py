"""Pytest wrappers for the executable stress suites.

The original suites remain executable scripts for backward compatibility.
This wrapper lets CI run them through pytest without rewriting every test at
once.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SUITES = [
    "dgm/stress_tests_dgm.py",
    "stress_tests.py",
    "stress_tests_v5.py",
    "stress_tests_v6.py",
    "stress_tests_v7_pflichtenheft.py",
    "stress_tests_v8.py",
    "stress_tests_a2_drel.py",
    "stress_tests_a3.py",
    "stress_tests_a4.py",
    "stress_tests_v9.py",
    "stress_tests_v9_baseline.py",
    "stress_tests_v9_classification.py",
    "stress_tests_v9_consistency.py",
    "stress_tests_v9_gating_anchor.py",
    "stress_tests_v9_keydrift.py",
    "stress_tests_v9_priority.py",
    "stress_tests_v9_property.py",
    "stress_tests_v9_smoke.py",
    "stress_tests_v10_contracts.py",
    "stress_tests_v101_contracts.py",
    "stress_tests_v102_contracts.py",
    "stress_tests_v103_contracts.py",
    "stress_tests_v104_contracts.py",
    "stress_tests_v105_contracts.py",
    "stress_tests_v106_contracts.py",
    "stress_tests_v110_runtime.py",
    "stress_tests_v111_runtime.py",
    "stress_tests_v112_phase_runtime.py",
    "stress_tests_v113_phase_migration.py",
    "stress_tests_v114_safety_diagnostics.py",
    "stress_tests_v115_selfmod_boundary.py",
    "stress_tests_v116_runtime_operations.py",
    "stress_tests_v120_event_sourced_runtime.py",
]


def test_executable_stress_suites_pass():
    if os.getenv("RUN_LEGACY_SCRIPT_WRAPPER") != "1":
        pytest.skip("set RUN_LEGACY_SCRIPT_WRAPPER=1 to run legacy executable suites under pytest")
    env = dict(os.environ)
    # Do not force LLM_MODE here: legacy suites intentionally verify
    # backward-compatible USE_REAL_LLM fail-closed behavior.
    env.pop("LLM_MODE", None)
    env["LRSI_VERBOSE"] = "1"
    for suite in SUITES:
        result = subprocess.run(
            [sys.executable, suite],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        assert result.returncode == 0, f"{suite} failed:\n{result.stdout}"
