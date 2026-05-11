"""
LRSI V11.0 Runtime Core — Phase-Service PipelineRunner
====================================================================
V11.0 keeps runner.main() thin and moves high-risk phase responsibilities into service classes:

  Every mutation is a ChangeProposal that runs through DGM pre-checks
  before entering the governance pipeline. Pareto dominance replaces
  implicit scalar ranking within the admissible region.

  "Only the admissible may be optimized." (D2)

Pipeline (V11.0):
  0. GovernanceStage / MutationStage / DGMPrecheckStage
  1. CouncilStage / Baseline Decision
  2. Hold-Logik
  3. Attractor Layer (Σ, L, O, D → classify)
  3b. DREL + A3 + A4
  3c. DGM Post-Check (Pareto admissibility)
  4. Extended Gate (FINAL)
  5. Rollback (if required)
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from adversarial_orchestrator import MiniAdversarialOrchestrator
from agency_verifier import AgencyVerifier
from calibration import ShadowCalibrationRecorder, ShadowDecision
from config import BASE_PROMPT, ITERATIONS
from counter_check import CounterChecker
from dgm_bridge import DGMRunnerBridge
from evidence import EvidenceGenerator
from external_integrity import ExternalCommitLog
from governance_takt import GovernanceTakt
from human_coupling import HumanCouplingCheck
from human_override import HumanOverrideLayer
from lrsi_logging import configure_logging
from memory import MemoryStore
from memory_gate import MemoryGate
from mirror import reflect
from norm_erosion import NormErosionDetector
from path_model import PathModel
from pipeline.execution_plan import build_iteration_phases, build_phase_registry
from pipeline.phase_contexts import AdversarialPhaseContext, AuditPhaseContext
from pipeline.phase_runtime import ContextRegistry, PhaseExecutor
from pipeline.phase_services import (
    AdversarialPhase,
    AttractorPhase,
    AuditRecorder,
    CouncilPhase,
    FinalGatePhase,
    HoldLogicPhase,
    HumanReviewPhase,
    PersistencePhase,
    PostRunReporter,
)
from pipeline.records import build_dgm_pre_reject_record, build_review_record
from pipeline.runtime_helpers import (
    build_agent,
    build_attractor_state,
    extract_candidate_memory,
)
from pipeline.runtime_operations_phases import (
    EvaluationPhase as RuntimeEvaluationPhase,
    MemoryConsolidationPhase as RuntimeMemoryConsolidationPhase,
    ObservabilityPhase,
)
from pipeline.self_modification_phases import (
    DGMPostcheckPhase,
    DGMPrecheckPhase,
    MutationPhase,
    PreProposalAdversarialPhase,
)
from pipeline.stages import (
    A3Stage,
    A4Stage,
    AttractorStage,
    CouncilStage,
    DGMPrecheckStage,
    DRELStage,
    EvaluationStage,
    ExtendedGateStage,
    GovernanceStage,
    MutationStage,
    PersistenceStage,
)
from replay_critic import FullReplayEngine, PostHocCritic, build_snapshot
from roles import (
    CriticRole,
    GovernanceCouncil,
    HumanLiaisonRole,
    MemoryGuardRole,
    PolicyGuardRole,
    TruthAuditorRole,
    VerifierRole,
)
from semantic_drift import SemanticDriftMonitor
from storage import Storage
from truth_sensitivity import TruthSensitivityLayer
from version import SCHEMA_VERSION


@dataclass
class IterationContext:
    """Typed per-iteration contract surface for the structured runner.

    The contained values remain intentionally permissive (dict/list/Any) because
    the legacy safety modules still exchange rich diagnostics. The important V10.5 constraint is that phase ownership is explicit: every field is
    produced by a named phase/service and consumed by later named phases.
    """

    iteration: int
    parent_metrics: dict[str, Any] = field(default_factory=dict)
    previous_policy: dict[str, Any] | None = None
    previous_prompt: str | None = None
    system_state: dict[str, Any] = field(default_factory=dict)
    mode_transitioned: bool = False
    mode_adj: dict[str, Any] = field(default_factory=dict)
    adjusted: dict[str, Any] = field(default_factory=dict)
    prompt_meta: dict[str, Any] = field(default_factory=dict)
    policy_meta: dict[str, Any] = field(default_factory=dict)
    semantic_drift: dict[str, Any] = field(default_factory=dict)
    preproposal_adversarial: dict[str, Any] = field(default_factory=dict)
    evidence_bundle: dict[str, Any] | None = None
    shadow_observation: dict[str, Any] | None = None
    candidate: Any = None
    child_metrics: dict[str, Any] = field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = field(default_factory=list)
    phase_audit: list[dict[str, Any]] = field(default_factory=list)
    dgm_pre: Any = None
    dgm_proposal: Any = None
    dgm_allowed: bool = False
    dgm_reason: str = ""
    dgm_reqs: dict[str, Any] = field(default_factory=dict)
    verdicts: list[Any] = field(default_factory=list)
    gate_d: str = ""
    gate_r: Any = None
    gate_diag: dict[str, Any] = field(default_factory=dict)
    pg_d: str = ""
    pg_reasons: list[str] = field(default_factory=list)
    pg_diag: dict[str, Any] = field(default_factory=dict)
    cc_final: str = ""
    cc_reasons: list[str] = field(default_factory=list)
    cc_diag: dict[str, Any] = field(default_factory=dict)
    ts_d: str = ""
    ts_r: str = ""
    ts_diag: dict[str, Any] = field(default_factory=dict)
    council_decision: str = ""
    council_reasons: list[str] = field(default_factory=list)
    per_role: dict[str, Any] = field(default_factory=dict)
    dissent_info: dict[str, Any] = field(default_factory=dict)
    escalation_info: dict[str, Any] = field(default_factory=dict)
    hold_metrics: dict[str, Any] | None = None
    hold_resolved: bool = False
    council_accepted: bool = False
    human_override_record: dict[str, Any] | None = None
    erosion_status: str = ""
    erosion_reason: str = ""
    erosion_diag: dict[str, Any] = field(default_factory=dict)
    hc_d: str = ""
    hc_r: str = ""
    hc_diag: dict[str, Any] = field(default_factory=dict)
    path_status: str = ""
    path_reason: str = ""
    path_diag: dict[str, Any] = field(default_factory=dict)
    curr_state: Any = None
    attractor: str = ""
    trends: Any = None
    confidence: float | None = None
    gating_anchor: Any = None
    gating_anchor_source: str = "none"
    candidate_diagnostics: dict[str, Any] = field(default_factory=dict)
    sigma: float = 0.0
    l_val: float = 0.0
    o_val: float = 0.0
    d_val: float = 0.0
    sigma_comp: dict[str, Any] = field(default_factory=dict)
    l_comp: dict[str, Any] = field(default_factory=dict)
    o_comp: dict[str, Any] = field(default_factory=dict)
    d_comp: dict[str, Any] = field(default_factory=dict)
    drel_context: dict[str, Any] = field(default_factory=dict)
    ss_risk: float = 0.0
    ss_d_vis: float = 0.0
    ss_d_ind: float = 0.0
    ss_diag: dict[str, Any] = field(default_factory=dict)
    o_ext: float = 0.0
    o_combined: float = 0.0
    ext_rev_verified: bool = False
    ext_int_diag: dict[str, Any] = field(default_factory=dict)
    resonance_eligible: bool = False
    resonance_reason: str = ""
    drel_status: str = ""
    drel_reason: str = ""
    drel_diag: dict[str, Any] = field(default_factory=dict)
    real_agency: float = 0.0
    manip_risk: float = 0.0
    agency_diag: dict[str, Any] = field(default_factory=dict)
    axiom_risk: float = 0.0
    axiom_diag: dict[str, Any] = field(default_factory=dict)
    silence_risk: float = 0.0
    silence_diag: dict[str, Any] = field(default_factory=dict)
    proxy_risk: float = 0.0
    proxy_diag: dict[str, Any] = field(default_factory=dict)
    a4_max: float = 0.0
    dgm_admissible: bool = False
    dgm_quality: dict[str, Any] = field(default_factory=dict)
    dgm_post_diag: dict[str, Any] = field(default_factory=dict)
    sham_risk: float = 0.0
    sham_downgrade: bool = False
    sham_diag: dict[str, Any] = field(default_factory=dict)
    carrier_risk: float = 0.0
    carrier_block: bool = False
    carrier_diag: dict[str, Any] = field(default_factory=dict)
    complexity_admissible: bool = True
    complexity_risk: float = 0.0
    complexity_diag: dict[str, Any] = field(default_factory=dict)
    auxiliary: dict[str, Any] = field(default_factory=dict)
    ext_decision: str = ""
    ext_reason: str = ""
    ext_diag: dict[str, Any] = field(default_factory=dict)
    accepted: bool = False
    effective_policy: dict[str, Any] | None = None
    final_decision: str = ""
    memory_events: list[dict[str, Any]] = field(default_factory=list)
    reflection: dict[str, Any] | None = None
    trace_id: str = ""
    evaluation_diagnostics_v11_6: dict[str, Any] = field(default_factory=dict)
    memory_diagnostics_v11_6: dict[str, Any] = field(default_factory=dict)
    runtime_events_v11_6: list[dict[str, Any]] = field(default_factory=list)
    observability_v11_6: dict[str, Any] = field(default_factory=dict)
    phase_events_v12: list[dict[str, Any]] = field(default_factory=list)
    event_projection_v12: dict[str, Any] = field(default_factory=dict)
    audit_phase_context: AuditPhaseContext | None = None
    record: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    selfmod_mutation_v11_5: dict[str, Any] = field(default_factory=dict)
    selfmod_preproposal_v11_5: dict[str, Any] = field(default_factory=dict)
    selfmod_dgm_precheck_v11_5: dict[str, Any] = field(default_factory=dict)
    selfmod_dgm_postcheck_v11_5: dict[str, Any] = field(default_factory=dict)
    adversarial_phase_result: Any = None
    attractor_diagnostics: dict[str, Any] = field(default_factory=dict)
    adversarial_diagnostics: dict[str, Any] = field(default_factory=dict)


class PipelineRunner:
    """Structured V11.0 runtime facade.

    V11.0 keeps ``runner.main()`` thin and moves critical runtime responsibilities into
    explicit phase-service classes. The ordering preserves V10.4 safety semantics while
    making audit consistency and phase contracts directly testable.
    """

    def __init__(self, *, iterations=None, storage_path=None, memory_path=None,
                 simulation_mode=True, return_records=False, verbose=None, llm_client=None):
        self.iterations = iterations
        self.storage_path = storage_path
        self.memory_path = memory_path
        self.simulation_mode = simulation_mode
        self.return_records = return_records
        self.verbose = verbose
        self.logger = configure_logging(verbose)
        self.llm_client = llm_client

    def run(self):
        """Execute the pipeline through explicit top-level phases."""
        self.prepare_iteration_runtime()
        records = self.run_structured_iterations()
        return self.finish(records)

    def prepare_iteration_runtime(self):
        """Phase hook for runtime preparation and future dependency injection."""
        self._prepared = True

    def run_structured_iterations(self):
        """Run the structured V11.0 phase-service pipeline."""
        if not getattr(self, "_prepared", False):
            self.prepare_iteration_runtime()
        return PipelineExecution(
            iterations=self.iterations,
            storage_path=self.storage_path,
            memory_path=self.memory_path,
            simulation_mode=self.simulation_mode,
            return_records=True,
            verbose=self.verbose,
            llm_client=self.llm_client,
        ).run()

    def finish(self, records):
        """Phase hook for return-value shaping."""
        if self.return_records:
            return records
        return None


class PipelineExecution:
    """V11.0 structured pipeline execution.

    The class deliberately names the contract phases retained from V10.4 and delegates
    high-risk parts to V10.5 service classes:
    ``prepare_iteration``, ``run_mutation_contract``, ``run_council``,
    ``run_human_review``, ``run_attractor_checks``, ``run_adversarial_layers``,
    ``run_final_gate``, ``apply_or_reject_candidate`` and
    ``persist_iteration_record``.
    """

    def __init__(self, *, iterations=None, storage_path=None, memory_path=None,
                 simulation_mode=True, return_records=False, verbose=None, llm_client=None):
        self.iterations = iterations
        self.storage_path = storage_path
        self.memory_path = memory_path
        self.simulation_mode = simulation_mode
        self.return_records = return_records
        self.verbose = verbose
        self.logger = configure_logging(verbose)
        self.llm_client = llm_client
        self.initialize_runtime()

    def initialize_runtime(self):
        """Create long-lived modules and baseline anchors."""
        self.memory = (MemoryStore(self.memory_path) if self.memory_path
                       else MemoryStore())
        self.memory_gate = MemoryGate()
        self.storage = (
            Storage(self.storage_path, production_mode=not self.simulation_mode)
            if self.storage_path
            else Storage(production_mode=not self.simulation_mode)
        )

        self.erosion_detector = NormErosionDetector()
        self.counter_checker = CounterChecker()
        self.path_model = PathModel()
        self.truth_layer = TruthSensitivityLayer()
        self.human_check = HumanCouplingCheck()
        self.governance = GovernanceTakt()
        self.council = GovernanceCouncil()
        self.human_override = HumanOverrideLayer(simulation_mode=self.simulation_mode)
        self.replay_engine = FullReplayEngine()
        self.post_hoc_critic = PostHocCritic()
        self.agency_verifier = AgencyVerifier()
        self.external_commits = ExternalCommitLog()
        self.dgm_bridge = DGMRunnerBridge()

        self.role_verifier = VerifierRole()
        self.role_policy = PolicyGuardRole()
        self.role_critic = CriticRole()
        self.role_truth = TruthAuditorRole()
        self.role_memory = MemoryGuardRole()
        self.role_human = HumanLiaisonRole()

        self.governance_stage = GovernanceStage()
        self.evaluation_stage = EvaluationStage()
        self.mutation_stage = MutationStage()
        self.dgm_pre_stage = DGMPrecheckStage()
        self.council_stage = CouncilStage()
        self.attractor_stage = AttractorStage()
        self.drel_stage = DRELStage()
        self.a3_stage = A3Stage()
        self.a4_stage = A4Stage()
        self.extended_gate_stage = ExtendedGateStage()
        self.persistence_stage = PersistenceStage()
        self.phase_executor = PhaseExecutor()
        self.council_phase = CouncilPhase()
        self.hold_logic_phase = HoldLogicPhase()
        self.human_review_phase = HumanReviewPhase()
        self.final_gate_phase = FinalGatePhase()
        self.persistence_phase = PersistencePhase()
        self.audit_recorder = AuditRecorder()
        self.adversarial_phase = AdversarialPhase()
        self.attractor_phase = AttractorPhase()
        self.evaluation_phase = RuntimeEvaluationPhase()
        self.memory_phase = RuntimeMemoryConsolidationPhase()
        self.observability_phase = ObservabilityPhase()
        self.post_run_reporter = PostRunReporter()
        self.mutation_phase = MutationPhase()
        self.preproposal_adversarial_phase = PreProposalAdversarialPhase()
        self.dgm_precheck_phase = DGMPrecheckPhase()
        self.dgm_postcheck_phase = DGMPostcheckPhase()
        self.semantic_drift_monitor = SemanticDriftMonitor()
        self.preproposal_adversarial_orchestrator = MiniAdversarialOrchestrator()
        self.evidence_generator = EvidenceGenerator(self._load_threshold_registry())
        self.shadow_recorder = self._build_shadow_recorder()
        self.agent_builder = build_agent
        self.state_builder = build_attractor_state
        self.memory_extractor = extract_candidate_memory
        self.snapshot_builder = build_snapshot

        self.agent = self.agent_builder(BASE_PROMPT, self.memory, None, llm_client=self.llm_client)
        self.baseline_metrics = self.evaluation_stage.run(agent=self.agent).metrics
        self.iterations_in_mode = 0
        self.recent_reds = 0
        self.recent_yellows = 0
        self.all_records: list[dict[str, Any]] = []
        self.all_snapshots: list[dict[str, Any]] = []
        self.prev_attractor_state = None
        self.effective_attractor_state = None
        self.baseline_attractor_state = self.state_builder(
            self.baseline_metrics, history=[])

    @staticmethod
    def _load_threshold_registry() -> dict[str, Any]:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "runtime_config" / "threshold_registry.json"
        if not path.exists():
            return {"schema_version": SCHEMA_VERSION, "thresholds": []}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _build_shadow_recorder():
        import os

        path = os.getenv("SHADOW_CALIBRATION_PATH")
        if not path:
            return None
        return ShadowCalibrationRecorder(path)

    def run(self):
        n_iterations = self.iterations if self.iterations is not None else ITERATIONS
        for iteration in range(n_iterations):
            self.run_iteration(iteration)
        self.run_post_run_analysis()
        if self.return_records:
            return self.all_records
        return None

    def run_iteration(self, iteration: int):
        """Run one iteration through a declarative phase list.

        V11.2 no longer encodes the main loop as hard-coded method calls. The
        loop iterates phase objects. Fully migrated phases receive explicit
        input dataclasses and return immutable PhaseResult objects. Legacy
        phases are temporarily connected through MethodPhaseAdapter so the
        historical contract suites remain executable while migration continues.

        Compatibility phase names retained in the declarative list:
        prepare_iteration, run_mutation_contract, run_council,
        run_human_review, run_attractor_checks, run_adversarial_layers,
        run_final_gate, apply_or_reject_candidate, persist_iteration_record.
        """
        ctx = self.prepare_iteration(iteration)
        registry = self._phase_registry(ctx)
        for phase in self._build_iteration_phases():
            registry, result = self.phase_executor.execute(phase, registry, ctx=ctx)
            registry = self._phase_registry(ctx).merge_result(result)
            if result.terminal:
                return
        self.update_signal_tracking(ctx)
        self.print_iteration_summary(ctx)

    def _phase_registry(self, ctx: IterationContext) -> ContextRegistry:
        return build_phase_registry(self, ctx)

    def _build_iteration_phases(self):
        return build_iteration_phases(self)

    def prepare_iteration(self, iteration: int) -> IterationContext:
        import uuid
        ctx = IterationContext(iteration=iteration)
        ctx.trace_id = f"lrsi-{uuid.uuid4().hex[:16]}"
        ctx.parent_metrics = self.evaluation_stage.run(agent=self.agent).metrics
        ctx.previous_policy = deepcopy(self.agent.policy)
        ctx.previous_prompt = self.agent.prompt

        gov_out = self.governance_stage.run(
            governance=self.governance,
            erosion_detector=self.erosion_detector,
            path_model=self.path_model,
            recent_reds=self.recent_reds,
            recent_yellows=self.recent_yellows,
            iterations_in_mode=self.iterations_in_mode,
        )
        ctx.system_state = gov_out.system_state
        ctx.mode_transitioned = gov_out.mode_transitioned
        self.iterations_in_mode = gov_out.iterations_in_mode
        ctx.mode_adj = gov_out.mode_adjustments
        ctx.adjusted = gov_out.adjusted_thresholds
        return ctx

    def handle_review_mode(self, ctx: IterationContext) -> bool:
        if self.governance.current_mode() != "review":
            return False
        record = build_review_record(
            iteration=ctx.iteration,
            mode="review",
            parent_metrics=ctx.parent_metrics,
            previous_policy=ctx.previous_policy,
            trace_id=ctx.trace_id,
        )
        persisted = self.audit_recorder.persist(
            storage=self.storage,
            persistence_stage=self.persistence_stage,
            record=record,
            history=self.all_records,
        ).record
        ctx.record = persisted
        self.logger.info("[%s] mode=REVIEW — no changes", ctx.iteration)
        return True

    def run_mutation_contract(self, ctx: IterationContext) -> bool:
        mutation_out = self.mutation_stage.run(
            agent=self.agent,
            iteration=ctx.iteration,
            allow_policy_change=ctx.mode_adj["allow_policy_change"],
            previous_policy=ctx.previous_policy,
        )
        ctx.prompt_meta = mutation_out.prompt_meta
        ctx.policy_meta = mutation_out.policy_meta
        ctx.semantic_drift = self.semantic_drift_monitor.compare(
            self.baseline_attractor_state.prompt if hasattr(self.baseline_attractor_state, "prompt") else BASE_PROMPT,
            ctx.prompt_meta.get("new_prompt", ""),
        ).to_dict()
        ctx.preproposal_adversarial = self.preproposal_adversarial_orchestrator.attack(
            prompt_meta=ctx.prompt_meta,
            policy_meta=ctx.policy_meta,
        )
        ctx.prompt_meta["semantic_drift"] = ctx.semantic_drift
        ctx.prompt_meta["preproposal_adversarial"] = ctx.preproposal_adversarial

        ctx.dgm_pre = self.dgm_pre_stage.run(
            bridge=self.dgm_bridge,
            prompt_meta=ctx.prompt_meta,
            policy_meta=ctx.policy_meta,
            iteration=ctx.iteration,
        )
        ctx.dgm_proposal = ctx.dgm_pre.proposal
        ctx.dgm_allowed = ctx.dgm_pre.allowed
        ctx.dgm_reason = ctx.dgm_pre.reason
        ctx.dgm_reqs = ctx.dgm_pre.requirements

        if not ctx.dgm_allowed:
            gating_anchor_source = (
                "effective" if self.effective_attractor_state is not None
                else "baseline" if self.baseline_attractor_state is not None
                else "none"
            )
            gating_anchor = (
                self.effective_attractor_state if self.effective_attractor_state is not None
                else self.baseline_attractor_state
            )
            record = build_dgm_pre_reject_record(
                iteration=ctx.iteration,
                mode=self.governance.current_mode(),
                parent_metrics=ctx.parent_metrics,
                baseline_metrics=self.baseline_metrics,
                previous_policy=ctx.previous_policy,
                candidate_policy=ctx.policy_meta.get("new_policy"),
                proposal=ctx.dgm_proposal,
                dgm_reason=ctx.dgm_reason,
                dgm_requirements=ctx.dgm_reqs,
                gating_anchor_source=gating_anchor_source,
                gating_anchor=gating_anchor,
            )
            persisted = self.audit_recorder.persist(
                storage=self.storage,
                persistence_stage=self.persistence_stage,
                record=record,
                history=self.all_records,
            ).record
            ctx.record = persisted
            self.logger.info("[%s] DGM_PRE_REJECT: %s", ctx.iteration, ctx.dgm_reason)
            return False

        ctx.candidate = self.agent_builder(
            ctx.prompt_meta["new_prompt"], self.memory, ctx.policy_meta["new_policy"],
            llm_client=self.agent.llm)
        ctx.child_metrics = self.evaluation_stage.run(agent=ctx.candidate).metrics
        ctx.decision_trace.append(ctx.dgm_pre.trace.trace_entry())
        return True

    def run_council(self, ctx: IterationContext):
        """Legacy compatibility wrapper; declarative loop uses CouncilPhase directly.

        Historical contract note: this replaces self.council_phase.run with the
        PhaseExecutor seam while keeping the old method name callable.
        """
        registry, _ = self.phase_executor.execute(
            self.council_phase, self._phase_registry(ctx), ctx=ctx)
        return registry

    def run_hold_logic(self, ctx: IterationContext):
        ctx.hold_metrics = None
        ctx.hold_resolved = False
        ctx.council_accepted = False
        if ctx.council_decision == "GREEN":
            ctx.council_accepted = True
        elif ctx.council_decision == "YELLOW":
            ctx.hold_metrics = self.evaluation_stage.run(
                agent=ctx.candidate, mode="extended").metrics
            threshold = ctx.candidate.policy["hold_policy"]["extended_eval_threshold"]
            if (ctx.hold_metrics["extended_accuracy"] >= threshold
                    and ctx.hold_metrics["suspicious_rate"] <= 0.20):
                ctx.council_accepted = True
                ctx.hold_resolved = True
        ctx.decision_trace.append({
            "stage": "hold",
            "decision": "ACCEPT" if ctx.council_accepted else "HOLD",
            "reason": "hold_resolved" if ctx.hold_resolved else (
                "council_green" if ctx.council_accepted else "blocked"),
        })

    def run_human_review(self, ctx: IterationContext):
        result = self.human_review_phase.run(
            iteration=ctx.iteration,
            human_override=self.human_override,
            council_decision=ctx.council_decision,
            council_reasons=ctx.council_reasons,
            council_accepted=ctx.council_accepted,
            verdicts=ctx.verdicts,
            dissent_info=ctx.dissent_info,
            escalation_info=ctx.escalation_info,
            path_model=self.path_model,
            erosion_detector=self.erosion_detector,
            truth_status=ctx.ts_d,
            governance_mode=self.governance.current_mode(),
            dgm_requirements=ctx.dgm_reqs,
            dgm_reason=ctx.dgm_reason,
        )
        ctx.council_decision = result.council_decision
        ctx.council_accepted = result.council_accepted
        ctx.human_override_record = result.override_record
    def run_erosion_and_human_coupling(self, ctx: IterationContext):
        self.erosion_detector.record(ctx.iteration, self.agent.policy,
                                     ctx.candidate.policy, ctx.council_accepted,
                                     ctx.council_decision, ctx.hold_resolved)
        ctx.erosion_status, ctx.erosion_reason, ctx.erosion_diag = (
            self.erosion_detector.check())
        if ctx.erosion_status == "RED" and ctx.council_accepted:
            ctx.council_accepted = False
            ctx.council_decision = "RED"
            ctx.council_reasons.append(f"erosion_override:{ctx.erosion_reason}")

        iter_rec: dict[str, Any] = {
            "gate_decision": ctx.council_decision,
            "gate_reason": "|".join(ctx.council_reasons),
            "gate_diagnostics": ctx.gate_diag,
            "hold_metrics": ctx.hold_metrics, "memory_events": [],
            "reflection": None, "prompt_mutation": ctx.prompt_meta,
            "policy_mutation": ctx.policy_meta,
            "policy_gate": {"decision": ctx.pg_d, "reasons": ctx.pg_reasons},
            "counter_check": {"decision": ctx.cc_final,
                              "reasons": ctx.cc_reasons,
                              "diagnostics": ctx.cc_diag},
            "truth_sensitivity": {"decision": ctx.ts_d, "reason": ctx.ts_r,
                                  "diagnostics": ctx.ts_diag},
        }
        ctx.hc_d, ctx.hc_r, ctx.hc_diag = self.human_check.check(iter_rec)
        ctx.verdicts.append(self.role_human.evaluate(ctx.hc_d, ctx.hc_r, ctx.hc_diag))
        ctx.path_status, ctx.path_reason, ctx.path_diag = self.path_model.assess()

    def run_attractor_checks(self, ctx: IterationContext):
        attractor_context = {
            "metrics": ctx.child_metrics,
            "human_coupling": ctx.hc_diag,
            "roles_state": ctx.per_role,
            "memory_state": self.memory.lifecycle_stats(),
            "replay_consistency": 1.0,
            "truth_diag": ctx.ts_diag,
            "counter_check": {"decision": ctx.cc_final,
                              "reasons": ctx.cc_reasons,
                              "diagnostics": ctx.cc_diag},
            "human_override": ctx.human_override_record,
            "dissent": ctx.dissent_info,
            "council_per_role": ctx.per_role,
            "path_diag": ctx.path_diag,
            "gate_diag": ctx.gate_diag,
            "erosion_diag": ctx.erosion_diag,
            "history": self.all_records,
        }
        attractor_out = self.attractor_stage.run(
            build_state_fn=self.state_builder,
            metrics=ctx.child_metrics,
            history=self.all_records,
            context=attractor_context,
            effective_attractor_state=self.effective_attractor_state,
            baseline_attractor_state=self.baseline_attractor_state,
            previous_candidate_state=self.prev_attractor_state,
        )
        ctx.curr_state = attractor_out.current_state
        ctx.attractor = attractor_out.attractor
        ctx.trends = attractor_out.trends
        ctx.confidence = attractor_out.confidence
        ctx.gating_anchor = attractor_out.gating_anchor
        ctx.gating_anchor_source = attractor_out.gating_anchor_source
        ctx.candidate_diagnostics = attractor_out.candidate_diagnostics
        ctx.sigma = ctx.curr_state.sigma
        ctx.l_val = ctx.curr_state.l
        ctx.o_val = ctx.curr_state.o
        ctx.d_val = ctx.curr_state.d
        ctx.sigma_comp = ctx.curr_state.sigma_components
        ctx.l_comp = ctx.curr_state.l_components
        ctx.o_comp = ctx.curr_state.o_components
        ctx.d_comp = ctx.curr_state.d_components
        ctx.decision_trace.append({
            "stage": "attractor", "decision": ctx.attractor,
            "reason": (f"Σ={ctx.sigma:.3f} L={ctx.l_val:.3f} "
                       f"O={ctx.o_val:.3f} D={ctx.d_val:.3f} "
                       f"anchor={ctx.gating_anchor_source}"),
        })
        if ctx.candidate_diagnostics:
            ctx.decision_trace.append({
                "stage": "attractor_candidate_diagnostic",
                "decision": "DIAGNOSTIC",
                "reason": (f"vs_rejected_candidate: "
                           f"attr={ctx.candidate_diagnostics['attractor']} "
                           f"(NOT gating-relevant)"),
            })

    def run_adversarial_layers(self, ctx: IterationContext):
        result = self.adversarial_phase.run(
            ctx=ctx,
            stages={
                "a3": self.a3_stage,
                "a4": self.a4_stage,
                "drel": self.drel_stage,
            },
            services={
                "external_commits": self.external_commits,
                "agency_verifier": self.agency_verifier,
                "dgm_bridge": self.dgm_bridge,
                "prev_attractor_state": self.prev_attractor_state,
            },
            history=self.all_records,
            phase_context=AdversarialPhaseContext.from_iteration(ctx),
        )
        result.apply_to(ctx)
        ctx.adversarial_phase_result = result

    def run_final_gate(self, ctx: IterationContext):
        result = self.final_gate_phase.run(
            extended_gate_stage=self.extended_gate_stage,
            council_decision=ctx.council_decision,
            attractor=ctx.attractor,
            trends=ctx.trends,
            current_state=ctx.curr_state,
            drel_status=ctx.drel_status,
            drel_reason=ctx.drel_reason,
            drel_diagnostics=ctx.drel_diag,
            real_agency=ctx.real_agency,
            agency_diagnostics=ctx.agency_diag,
            sincerity_risk=ctx.ss_risk,
            sincerity_diagnostics=ctx.ss_diag,
            external_reversibility_verified=ctx.ext_rev_verified,
            external_openness=ctx.o_ext,
            external_diagnostics=ctx.ext_int_diag,
            dissent_independence=ctx.ss_d_ind,
            dissent_visibility=ctx.ss_d_vis,
            axiom_risk=ctx.axiom_risk,
            axiom_diagnostics=ctx.axiom_diag,
            silence_risk=ctx.silence_risk,
            silence_diagnostics=ctx.silence_diag,
            proxy_risk=ctx.proxy_risk,
            proxy_diagnostics=ctx.proxy_diag,
            dgm_admissible=ctx.dgm_admissible,
            dgm_post_diagnostics=ctx.dgm_post_diag,
            sham_risk=ctx.sham_risk,
            sham_downgrade=ctx.sham_downgrade,
            sham_diagnostics=ctx.sham_diag,
            carrier_risk=ctx.carrier_risk,
            carrier_block=ctx.carrier_block,
            carrier_diagnostics=ctx.carrier_diag,
            complexity_admissible=ctx.complexity_admissible,
            complexity_risk=ctx.complexity_risk,
            complexity_diagnostics=ctx.complexity_diag,
            auxiliary=ctx.auxiliary,
        )
        ctx.attractor = result.attractor
        ctx.ext_decision = result.decision
        ctx.ext_reason = result.reason
        ctx.ext_diag = result.diagnostics
        ctx.decision_trace.append({
            "stage": "extended", "decision": ctx.ext_decision,
            "reason": ctx.ext_reason,
        })
    def apply_or_reject_candidate(self, ctx: IterationContext):
        ctx.accepted = (ctx.ext_decision == "GO")
        if ctx.ext_decision == "ROLLBACK":
            self.agent = self.agent_builder(ctx.previous_prompt, self.memory,
                                     ctx.previous_policy, llm_client=self.agent.llm)
        if ctx.accepted:
            self.agent = ctx.candidate
            self.external_commits.record(
                action=f"policy_mutation_iter_{ctx.iteration}",
                iteration=ctx.iteration,
                irreversibility=min(0.8, 0.3 + ctx.sigma * 0.5),
                rollback_available=True,
                verification_source="runner_self_report",
                domain="agent_policy",
                resolved=False,
            )
        self.prev_attractor_state = ctx.curr_state
        if ctx.accepted:
            self.effective_attractor_state = ctx.curr_state
        ctx.effective_policy = deepcopy(self.agent.policy)
        ctx.final_decision = ctx.ext_decision

    def run_post_decision_accounting(self, ctx: IterationContext):
        """Record post-decision path/reflection after declarative memory consolidation."""
        policy_changed = ctx.policy_meta.get("description", "") != "suppressed_by_mode"
        self.path_model.record_iteration(
            ctx.iteration, self.agent.prompt, self.agent.policy,
            ctx.accepted, ctx.final_decision, ctx.memory_events,
            policy_changed=(policy_changed and ctx.accepted),
            mode_transition=ctx.mode_transitioned)
        ctx.path_status, ctx.path_reason, ctx.path_diag = self.path_model.assess()
        gate_tuple = (ctx.council_decision, "|".join(ctx.council_reasons),
                      {"per_role": ctx.per_role, "dissent": ctx.dissent_info})
        policy_gate_result = (ctx.pg_d, ctx.pg_reasons, ctx.pg_diag)
        ctx.reflection = reflect(ctx.parent_metrics, ctx.child_metrics,
                                 gate_tuple, policy_gate_result)

    def consolidate_memory(self, ctx: IterationContext):
        """Legacy helper retained for old tests; new loop uses MemoryConsolidationPhase."""
        registry, _ = self.phase_executor.execute(
            self.memory_phase, self._phase_registry(ctx), ctx=ctx)
        return registry

    def persist_iteration_record(self, ctx: IterationContext):
        ctx.snapshot = build_snapshot(
            iteration=ctx.iteration,
            parent_metrics=ctx.parent_metrics, child_metrics=ctx.child_metrics,
            baseline_metrics=self.baseline_metrics,
            parent_policy=ctx.previous_policy,
            child_policy=ctx.candidate.policy,
            mode=self.governance.current_mode(),
            mode_adjustments=ctx.mode_adj,
            council_decision=ctx.council_decision,
            council_reasons=ctx.council_reasons, per_role=ctx.per_role,
            erosion_state=ctx.erosion_status,
            human_decision=ctx.human_override_record)
        self.all_snapshots.append(ctx.snapshot)
        ctx.audit_phase_context = AuditPhaseContext.from_iteration(ctx)
        if ctx.final_decision in {"HOLD", "STOP", "ROLLBACK", "RED"} or ctx.council_decision in {"RED", "YELLOW"}:
            ctx.evidence_bundle = self.evidence_generator.generate(ctx).to_dict()
        raw_record = self.build_iteration_record(ctx)
        if self.shadow_recorder is not None:
            shadow = ShadowDecision(
                run_id="pending-until-persisted",
                iteration=ctx.iteration,
                gate_decision=ctx.council_decision,
                final_decision=ctx.final_decision,
                human_decision=(ctx.human_override_record or {}).get("action", "not_reviewed"),
                thresholds=ctx.adjusted,
                diagnostics={"extended_gate": ctx.ext_diag, "semantic_drift": ctx.semantic_drift},
            )
            ctx.shadow_observation = shadow.to_dict()
            raw_record["shadow_observation"] = ctx.shadow_observation
        ctx.record = self.audit_recorder.persist(
            storage=self.storage,
            persistence_stage=self.persistence_stage,
            record=raw_record,
            history=self.all_records,
        ).record
        ctx.event_projection_v12 = self.storage.project_events()
        if self.shadow_recorder is not None and ctx.shadow_observation is not None:
            ctx.shadow_observation["run_id"] = ctx.record.get("run_id", "unknown")
            self.shadow_recorder.append(ShadowDecision(**ctx.shadow_observation))

    def build_iteration_record(self, ctx: IterationContext) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "trace_id": ctx.trace_id,
            "iteration": ctx.iteration,
            "mode": self.governance.current_mode(),
            "adjusted_thresholds": ctx.adjusted,
            "parent_metrics": ctx.parent_metrics,
            "child_metrics": ctx.child_metrics,
            "baseline_metrics": self.baseline_metrics,
            "gate_decision": ctx.council_decision,
            "gate_reason": "|".join(ctx.council_reasons),
            "gate_diagnostics": ctx.gate_diag,
            "council": ctx.per_role, "dissent": ctx.dissent_info,
            "escalation": ctx.escalation_info,
            "policy_gate": {"decision": ctx.pg_d, "reasons": ctx.pg_reasons,
                            "diagnostics": ctx.pg_diag},
            "counter_check": {"decision": ctx.cc_final, "reasons": ctx.cc_reasons,
                              "diagnostics": ctx.cc_diag},
            "truth_sensitivity": {"decision": ctx.ts_d, "reason": ctx.ts_r,
                                  "diagnostics": ctx.ts_diag},
            "erosion": {"status": ctx.erosion_status,
                        "reason": ctx.erosion_reason,
                        "diagnostics": ctx.erosion_diag},
            "path_model": {"status": ctx.path_status, "reason": ctx.path_reason,
                           "diagnostics": ctx.path_diag},
            "human_coupling": {"decision": ctx.hc_d, "reason": ctx.hc_r,
                               "diagnostics": ctx.hc_diag},
            "human_override": ctx.human_override_record,
            "attractor_state": ctx.curr_state.to_dict(),
            "attractor_gating_anchor": ctx.gating_anchor_source,
            "attractor_gating_anchor_state": (
                ctx.gating_anchor.to_dict() if ctx.gating_anchor is not None else None),
            "attractor_candidate_diagnostic": ctx.candidate_diagnostics,
            "attractor_diagnostics_v11_4": ctx.attractor_diagnostics,
            "adversarial_diagnostics_v11_4": ctx.adversarial_diagnostics,
            "drel": {"status": ctx.drel_status, "reason": ctx.drel_reason,
                     "diagnostics": ctx.drel_diag},
            "agency": {"real_agency": ctx.real_agency,
                       "manipulation_risk": ctx.manip_risk,
                       "diagnostics": ctx.agency_diag},
            "a3_sincerity": {
                "synthetic_sincerity_risk": ctx.ss_risk,
                "dissent_visibility": ctx.ss_d_vis,
                "dissent_independence": ctx.ss_d_ind,
                "diagnostics": ctx.ss_diag,
            },
            "a3_external": {
                "o_external": ctx.o_ext,
                "o_combined": ctx.o_combined,
                "external_reversibility_verified": ctx.ext_rev_verified,
                "diagnostics": ctx.ext_int_diag,
            },
            "extended_gate": {"decision": ctx.ext_decision,
                              "reason": ctx.ext_reason,
                              "diagnostics": ctx.ext_diag},
            "previous_policy": ctx.previous_policy,
            "candidate_policy": ctx.candidate.policy,
            "effective_policy": ctx.effective_policy,
            "final_decision": ctx.final_decision,
            "dgm": {
                "proposal": ctx.dgm_proposal.to_dict(),
                "pre_check": {"allowed": True, "reason": ctx.dgm_reason,
                              "requirements": ctx.dgm_reqs},
                "post_check": ctx.dgm_post_diag,
            },
            "self_modification_boundary_v11_5": {
                "mutation": ctx.selfmod_mutation_v11_5,
                "preproposal": ctx.selfmod_preproposal_v11_5,
                "dgm_precheck": ctx.selfmod_dgm_precheck_v11_5,
                "dgm_postcheck": ctx.selfmod_dgm_postcheck_v11_5,
            },
            "runtime_operations_v11_6": {
                "evaluation": ctx.evaluation_diagnostics_v11_6,
                "memory_consolidation": ctx.memory_diagnostics_v11_6,
                "observability": ctx.observability_v11_6,
                "runtime_events": ctx.runtime_events_v11_6,
            },
            "event_sourcing_v12_0": {
                "source_of_truth": "append_only_event_store",
                "phase_event_count": len(ctx.phase_events_v12),
                "projection_available": bool(ctx.event_projection_v12),
                "materialized_events_shape": "committed_event_refs",
            },
            # Storage.log_iteration replaces these provisional phase events with
            # committed event refs after append, so the materialized record does
            # not carry non-canonical sequence/hash values or full event payloads.
            "events_v12": ctx.phase_events_v12,
            "decision_trace": ctx.decision_trace,
            "phase_audit": ctx.phase_audit,
            "accepted": ctx.accepted,
            "hold_metrics": ctx.hold_metrics,
            "reflection": ctx.reflection,
            "memory_events": ctx.memory_events,
            "memory_lifecycle": self.memory.lifecycle_stats(),
            "active_prompt": self.agent.prompt,
            "prompt_mutation": ctx.prompt_meta,
            "policy_mutation": ctx.policy_meta,
            "semantic_drift": ctx.semantic_drift,
            "preproposal_adversarial": ctx.preproposal_adversarial,
            "evidence_bundle": ctx.evidence_bundle,
            "governance_takt": {"mode": self.governance.current_mode(),
                                "history": self.governance.history,
                                "adjustments": ctx.mode_adj},
        }

    def update_signal_tracking(self, ctx: IterationContext):
        if ctx.council_decision == "RED":
            self.recent_reds += 1
        else:
            self.recent_reds = max(0, self.recent_reds - 1)
        if ctx.council_decision == "YELLOW":
            self.recent_yellows += 1
        else:
            self.recent_yellows = max(0, self.recent_yellows - 1)

    def print_iteration_summary(self, ctx: IterationContext):
        trend_str = ""
        if ctx.trends:
            trend_str = (f" ΔΣ={ctx.trends.d_sigma:+.3f} "
                         f"ΔL={ctx.trends.d_l:+.3f} "
                         f"ΔO={ctx.trends.d_o:+.3f} "
                         f"ΔD={ctx.trends.d_d:+.3f}")
        self.logger.info(
            "[%s] mode=%s council=%s ext=%s drel=%s agency=%.2f "
            "ss=%.3f o_ext=%.3f attractor=%s accepted=%s "
            "Σ=%.3f L=%.3f O=%.3f D=%.3f%s",
            ctx.iteration, self.governance.current_mode(), ctx.council_decision,
            ctx.ext_decision, ctx.drel_status, ctx.real_agency, ctx.ss_risk,
            ctx.o_ext, ctx.attractor, ctx.accepted, ctx.sigma, ctx.l_val,
            ctx.o_val, ctx.d_val, trend_str,
        )

    def run_post_run_analysis(self):
        registry = ContextRegistry({
            "replay_engine": self.replay_engine,
            "snapshots": self.all_snapshots,
            "post_hoc_critic": self.post_hoc_critic,
            "records": self.all_records,
            "human_override": self.human_override,
            "memory": self.memory,
            "path_model": self.path_model,
            "effective_attractor_state": self.effective_attractor_state,
            "prev_attractor_state": self.prev_attractor_state,
            "logger": self.logger,
        })
        phase_input = self.post_run_reporter.build_input(registry)
        result = self.post_run_reporter.run(phase_input)
        self.post_run_report = result.patch.get("post_run_report") if hasattr(result, "patch") else result


def _run_pipeline_legacy_semantics(iterations=None, storage_path=None, memory_path=None,
                                   simulation_mode=True, return_records=False, verbose=None,
                                   llm_client=None):
    """Backward-compatible V11.0 wrapper around the structured runner."""
    return PipelineExecution(
        iterations=iterations,
        storage_path=storage_path,
        memory_path=memory_path,
        simulation_mode=simulation_mode,
        return_records=return_records,
        verbose=verbose,
        llm_client=llm_client,
    ).run()


def main(iterations=None, storage_path=None, memory_path=None,
         simulation_mode=True, return_records=False, verbose=None, llm_client=None):
    return PipelineRunner(
        iterations=iterations,
        storage_path=storage_path,
        memory_path=memory_path,
        simulation_mode=simulation_mode,
        return_records=return_records,
        verbose=verbose,
        llm_client=llm_client,
    ).run()


if __name__ == "__main__":
    main()
