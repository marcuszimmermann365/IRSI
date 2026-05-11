import inspect
import json
import subprocess
import sys

from agent import Agent
from eval import evaluate
from llm_client import LLMClient
from pipeline.phase_contexts import AdversarialPhaseContext, AuditPhaseContext
from pipeline.phase_services import AdversarialPhase, MemoryConsolidationPhase, PostRunReporter
from pipeline.runner_core import PipelineExecution
from runner import main
from storage import AppendOnlyAuditBackend, Storage, verify_hash_chain
from version import SCHEMA_VERSION


class NonDeepcopyableClient:
    def __init__(self, response="4"):
        self.calls = 0
        self.response = response

    def __deepcopy__(self, memo):  # pragma: no cover - failure path if deepcopy reappears
        raise AssertionError("LLM client must not be deep-copied")

    def generate(self, prompt, system_prompt=None):
        self.calls += 1
        return self.response

    @staticmethod
    def is_error_response(response):
        return LLMClient.is_error_response(response)


def test_version_single_source_of_truth_v106():
    assert SCHEMA_VERSION in {"10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0"}


def test_agent_accepts_injected_llm_and_evaluation_does_not_deepcopy_client():
    client = NonDeepcopyableClient("4")
    agent = Agent(prompt="base", llm_client=client)
    metrics = evaluate(agent)
    assert client.calls > 0
    assert metrics["llm_error_count"] == 0


def test_llm_errors_are_first_class_metrics():
    client = NonDeepcopyableClient("__LLM_ERROR__: simulated outage")
    agent = Agent(prompt="base", llm_client=client)
    metrics = evaluate(agent)
    assert metrics["llm_error_count"] > 0
    assert metrics["llm_error_rate"] > 0
    assert metrics["base_accuracy"] == 0


def test_pipeline_execution_reuses_injected_client_for_candidate(tmp_path):
    client = NonDeepcopyableClient("4")
    records = main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
        llm_client=client,
    )
    assert records
    assert client.calls > 0


def test_append_only_audit_backend_writes_jsonl_and_materialized_json(tmp_path):
    json_path = tmp_path / "run_log.json"
    backend = AppendOnlyAuditBackend(
        path=str(tmp_path / "run_log.jsonl"),
        materialized_json_path=str(json_path),
    )
    storage = Storage(backend=backend)
    first = storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    second = storage.log_iteration({"iteration": 1, "final_decision": "GO"})
    assert (tmp_path / "run_log.jsonl").read_text(encoding="utf-8").count("\n") == 2
    materialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert materialized == [first, second]
    ok, errors = verify_hash_chain(materialized)
    assert ok, errors


def test_adversarial_phase_and_smaller_phase_contexts_are_in_use():
    assert AdversarialPhase().name == "adversarial_phase"
    assert MemoryConsolidationPhase().name == "memory_consolidation_phase"
    assert PostRunReporter().name == "post_run_reporter"
    assert inspect.isclass(AdversarialPhaseContext)
    assert inspect.isclass(AuditPhaseContext)
    src = inspect.getsource(PipelineExecution.run_adversarial_layers)
    assert "self.adversarial_phase.run" in src
    assert "AdversarialPhaseContext.from_iteration" in src


def test_runner_is_quiet_by_default(tmp_path, capsys):
    main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    captured = capsys.readouterr()
    assert captured.out == ""


def test_record_live_fixtures_script_is_present_and_refuses_without_live_mode():
    result = subprocess.run(
        [sys.executable, "scripts/record_live_fixtures.py", "--limit", "1"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode != 0
    assert "LLM_MODE=live" in result.stdout


def test_ci_executes_static_tools():
    ci = open(".github/workflows/ci.yml", encoding="utf-8").read()
    assert "ruff check" in ci
    assert "bandit -q" in ci
    assert "mypy" in ci
