"""Iteration phase-plan and registry builders for ``PipelineExecution``.

The runtime core owns mutable execution state; this module owns the declarative
phase plan and the large registry surface needed by migrated phases.  That
keeps ``PipelineExecution`` focused on orchestration and state transitions.
"""

from __future__ import annotations

from typing import Any

from config import BASE_PROMPT
from pipeline.phase_contexts import ImmutablePhaseContext
from pipeline.phase_runtime import ContextRegistry, MethodPhaseAdapter


def build_phase_registry(execution: Any, ctx: Any) -> ContextRegistry:
    phase_context = ImmutablePhaseContext.from_iteration(ctx)
    return ContextRegistry.from_context(
        ctx,
        immutable_phase_context=phase_context,
        governance_mode=execution.governance.current_mode(),
        adjusted_thresholds=ctx.adjusted,
        allow_policy_change=ctx.mode_adj.get("allow_policy_change", True),
        baseline_metrics=execution.baseline_metrics,
        baseline_prompt=BASE_PROMPT,
        build_agent_fn=execution.agent_builder,
        agent=execution.agent,
        role_verifier=execution.role_verifier,
        role_policy=execution.role_policy,
        role_critic=execution.role_critic,
        role_truth=execution.role_truth,
        role_memory=execution.role_memory,
        counter_checker=execution.counter_checker,
        truth_layer=execution.truth_layer,
        council_stage=execution.council_stage,
        council=execution.council,
        dgm_requirements=ctx.dgm_reqs,
        evaluation_stage=execution.evaluation_stage,
        mutation_stage=execution.mutation_stage,
        dgm_pre_stage=execution.dgm_pre_stage,
        semantic_drift_monitor=execution.semantic_drift_monitor,
        preproposal_adversarial_orchestrator=execution.preproposal_adversarial_orchestrator,
        human_override=execution.human_override,
        path_model=execution.path_model,
        memory=execution.memory,
        memory_gate=execution.memory_gate,
        extract_candidate_memory_fn=execution.memory_extractor,
        logger=execution.logger,
        build_state_fn=execution.state_builder,
        attractor_stage=execution.attractor_stage,
        effective_attractor_state=execution.effective_attractor_state,
        baseline_attractor_state=execution.baseline_attractor_state,
        prev_attractor_state=execution.prev_attractor_state,
        a3_stage=execution.a3_stage,
        a4_stage=execution.a4_stage,
        drel_stage=execution.drel_stage,
        external_commits=execution.external_commits,
        agency_verifier=execution.agency_verifier,
        dgm_bridge=execution.dgm_bridge,
        erosion_detector=execution.erosion_detector,
        extended_gate_stage=execution.extended_gate_stage,
        storage=execution.storage,
        persistence_stage=execution.persistence_stage,
        audit_recorder=execution.audit_recorder,
        history=execution.all_records,
        snapshots=execution.all_snapshots,
        evidence_generator=execution.evidence_generator,
        shadow_recorder=execution.shadow_recorder,
        build_snapshot_fn=execution.snapshot_builder,
        build_record_fn=execution.build_iteration_record,
    )


def build_iteration_phases(execution: Any) -> list[Any]:
    return [
        MethodPhaseAdapter(
            name="review_mode",
            method=execution.handle_review_mode,
            decision="CHECKED",
            terminal_on=lambda outcome: bool(outcome),
            reason_fn=lambda outcome: "review_mode_active" if outcome else "not_review",
        ),
        execution.mutation_phase,
        execution.preproposal_adversarial_phase,
        execution.dgm_precheck_phase,
        execution.evaluation_phase,
        execution.council_phase,
        execution.hold_logic_phase,
        execution.human_review_phase,
        MethodPhaseAdapter(
            name="erosion_and_human_coupling",
            method=execution.run_erosion_and_human_coupling,
        ),
        execution.attractor_phase,
        execution.adversarial_phase,
        execution.dgm_postcheck_phase,
        execution.final_gate_phase,
        MethodPhaseAdapter(
            name="apply_or_reject_candidate",
            method=execution.apply_or_reject_candidate,
        ),
        execution.memory_phase,
        MethodPhaseAdapter(
            name="post_decision_accounting",
            method=execution.run_post_decision_accounting,
        ),
        execution.observability_phase,
        execution.persistence_phase,
    ]
