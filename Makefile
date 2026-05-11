.PHONY: compile test contract contract-quiet audit-invariants static static-soft legacy check full-check clean

compile:
	python -m compileall -q .

test:
	python -m pytest -q -rs

contract:
	python stress_tests_v110_runtime.py
	python stress_tests_v111_runtime.py
	python stress_tests_v112_phase_runtime.py
	python stress_tests_v113_phase_migration.py
	python stress_tests_v114_safety_diagnostics.py
	python stress_tests_v115_selfmod_boundary.py
	python stress_tests_v116_runtime_operations.py
	python stress_tests_v120_event_sourced_runtime.py

contract-quiet:
	@python stress_tests_v110_runtime.py >/tmp/lrsi_stress_v110.log && echo "stress v110 passed"
	@python stress_tests_v111_runtime.py >/tmp/lrsi_stress_v111.log && echo "stress v111 passed"
	@python stress_tests_v112_phase_runtime.py >/tmp/lrsi_stress_v112.log && echo "stress v112 passed"
	@python stress_tests_v113_phase_migration.py >/tmp/lrsi_stress_v113.log && echo "stress v113 passed"
	@python stress_tests_v114_safety_diagnostics.py >/tmp/lrsi_stress_v114.log && echo "stress v114 passed"
	@python stress_tests_v115_selfmod_boundary.py >/tmp/lrsi_stress_v115.log && echo "stress v115 passed"
	@python stress_tests_v116_runtime_operations.py >/tmp/lrsi_stress_v116.log && echo "stress v116 passed"
	@python stress_tests_v120_event_sourced_runtime.py >/tmp/lrsi_stress_v120.log && echo "stress v120 passed"
	@echo "contract suites passed"

audit-invariants:
	python scripts/check_phase_event_coverage.py --run-sample --iterations 3

static:
	python -m ruff check .
	python -m bandit -q -c pyproject.toml -r . -x './tests,./stress_tests*.py,./dgm/stress_tests_dgm.py,./scenario_*.py,./bewaehrungsstrecke.py'
	python -m mypy pipeline_contracts.py pipeline/phase_contexts.py pipeline/phase_runtime.py pipeline/phase_services.py pipeline/phase_council.py pipeline/phase_flow.py pipeline/phase_safety.py pipeline/self_modification_phases.py pipeline/runtime_operations_phases.py pipeline/execution_plan.py pipeline/runtime_helpers.py agent.py eval.py llm_client.py lrsi_logging.py storage.py eventsourcing.py runner.py

static-soft:
	@if command -v ruff >/dev/null 2>&1; then python -m ruff check .; else echo "ruff not installed; skipping local ruff"; fi
	@if command -v bandit >/dev/null 2>&1; then python -m bandit -q -c pyproject.toml -r . -x './tests,./stress_tests*.py,./dgm/stress_tests_dgm.py,./scenario_*.py,./bewaehrungsstrecke.py'; else echo "bandit not installed; skipping local bandit"; fi
	@if command -v mypy >/dev/null 2>&1; then python -m mypy pipeline_contracts.py pipeline/phase_contexts.py pipeline/phase_runtime.py pipeline/phase_services.py pipeline/phase_council.py pipeline/phase_flow.py pipeline/phase_safety.py pipeline/self_modification_phases.py pipeline/runtime_operations_phases.py pipeline/execution_plan.py pipeline/runtime_helpers.py agent.py eval.py llm_client.py lrsi_logging.py storage.py eventsourcing.py runner.py; else echo "mypy not installed; skipping local mypy"; fi

legacy:
	RUN_LEGACY_SCRIPT_WRAPPER=1 python -m pytest tests/test_executable_suites.py -s

check: compile test audit-invariants static

full-check: compile test audit-invariants static contract-quiet

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -f run_log.json run_log.json.lock run_log.jsonl run_log.jsonl.lock run_log.json.events.jsonl run_log.json.events.jsonl.lock audit_events.jsonl audit_events.jsonl.lock *.cursor.json memory_store.json memory_store.json.lock
	rm -rf *.pending run_log.json.events.jsonl.pending audit_events.jsonl.pending
