"""Runtime helper functions extracted from the pipeline execution core.

Keeping candidate-memory extraction, agent construction and attractor-state
construction outside ``runner_core`` makes the execution class a coordinator
rather than a mixed bag of orchestration plus low-level helper logic.
"""

from __future__ import annotations

from typing import Any

from agent import Agent
from attractor_engine import SystemState
from be1_value_model import compute_l
from drift_pressure import compute_d
from openness_model import compute_o
from subject_model import compute_sigma


def extract_candidate_memory(
    meta_info: dict[str, Any],
    child_metrics: dict[str, float],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    new_prompt = meta_info["prompt_meta"]["new_prompt"]
    if child_metrics["base_accuracy"] > 0.8:
        entries.append({
            "content": f"Prompt pattern may improve base performance: {new_prompt}",
            "source": "eval:base",
            "kind": "heuristic",
            "metadata": {
                k: child_metrics[k]
                for k in ("base_accuracy", "shift_accuracy", "stress_accuracy")
            },
        })
    if child_metrics["stress_accuracy"] < 0.5:
        entries.append({
            "content": f"Prompt pattern may reduce robustness under stress: {new_prompt}",
            "source": "eval:stress",
            "kind": "warning",
            "metadata": {
                "stress_accuracy": child_metrics["stress_accuracy"],
                "base_accuracy": child_metrics["base_accuracy"],
            },
        })
    if child_metrics["shift_accuracy"] < 0.6:
        entries.append({
            "content": f"Prompt pattern may generalize poorly: {new_prompt}",
            "source": "eval:shift",
            "kind": "warning",
            "metadata": {
                "shift_accuracy": child_metrics["shift_accuracy"],
                "base_accuracy": child_metrics["base_accuracy"],
            },
        })
    return entries


def build_agent(
    prompt: str,
    memory_store: Any,
    policy: dict[str, Any] | None,
    llm_client: Any = None,
) -> Agent:
    return Agent(
        prompt=prompt,
        consolidated_memory=memory_store.data["consolidated"],
        policy=policy,
        llm_client=llm_client,
    )


def build_attractor_state(
    metrics: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    **extra_context: Any,
) -> SystemState:
    """Build a genuine baseline/candidate SystemState from metrics and context."""
    context: dict[str, Any] = {
        "metrics": metrics,
        "history": history or [],
        "human_coupling": {},
        "roles_state": {},
        "memory_state": {},
        "replay_consistency": 1.0,
        "truth_diag": {},
        "counter_check": {},
        "human_override": {},
        "dissent": {},
        "council_per_role": {},
        "path_diag": {},
        "gate_diag": {},
        "erosion_diag": {},
        **extra_context,
    }
    sigma, sigma_comp = compute_sigma(context)
    l_val, l_comp = compute_l(context)
    o_val, o_comp = compute_o(context)
    d_val, d_comp = compute_d(context)
    return SystemState(
        sigma=sigma,
        l=l_val,
        o=o_val,
        d=d_val,
        sigma_components=sigma_comp,
        l_components=l_comp,
        o_components=o_comp,
        d_components=d_comp,
    )
