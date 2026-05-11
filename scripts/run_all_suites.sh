#!/usr/bin/env bash
set -euo pipefail
export LRSI_VERBOSE=${LRSI_VERBOSE:-1}

for f in \
  dgm/stress_tests_dgm.py \
  stress_tests.py \
  stress_tests_v5.py \
  stress_tests_v6.py \
  stress_tests_v7_pflichtenheft.py \
  stress_tests_v8.py \
  stress_tests_a2_drel.py \
  stress_tests_a3.py \
  stress_tests_a4.py \
  stress_tests_v9.py \
  stress_tests_v9_baseline.py \
  stress_tests_v9_classification.py \
  stress_tests_v9_consistency.py \
  stress_tests_v9_gating_anchor.py \
  stress_tests_v9_keydrift.py \
  stress_tests_v9_priority.py \
  stress_tests_v9_property.py \
  stress_tests_v9_smoke.py \
  stress_tests_v10_contracts.py \
  stress_tests_v101_contracts.py \
  stress_tests_v102_contracts.py \
  stress_tests_v103_contracts.py \
  stress_tests_v104_contracts.py \
  stress_tests_v105_contracts.py \
  stress_tests_v106_contracts.py \
  stress_tests_v110_runtime.py \
  stress_tests_v111_runtime.py \
  stress_tests_v112_phase_runtime.py \
  stress_tests_v113_phase_migration.py \
  stress_tests_v114_safety_diagnostics.py \
  stress_tests_v115_selfmod_boundary.py \
  stress_tests_v116_runtime_operations.py \
  stress_tests_v120_event_sourced_runtime.py; do
  echo "RUN $f"
  python "$f"
done

echo "RUN scripts/check_phase_event_coverage.py --run-sample --iterations 3"
python scripts/check_phase_event_coverage.py --run-sample --iterations 3
