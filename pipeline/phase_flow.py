"""Core flow, review, persistence and reporting phase services.

P1 split from the former monolithic ``pipeline.phase_services`` module.
Only the active declarative implementations live here; pre-migration duplicate
classes were intentionally removed.
"""

from dataclasses import dataclass
from typing import Any

from eventsourcing import RuntimeEvent
from human_override import HumanOverrideLayer
from pipeline.phase_runtime import ContextRegistry, PhaseResult
from pipeline.stages import require_human_review_from_dgm
from sham_resonance import SHAM_RESONANCE_BLOCK


@dataclass
class HumanReviewPhaseResult:
    council_decision: str
    council_accepted: bool
    override_record: dict[str, Any] | None


@dataclass
class FinalGatePhaseResult:
    attractor: str
    decision: str
    reason: str
    diagnostics: dict[str, Any]


@dataclass
class AuditRecordResult:
    record: dict[str, Any]


class AuditRecorder:
    """Persist one audit record and return exactly the persisted representation."""

    name = "audit_recorder"

    def persist(
        self,
        *,
        storage: Any,
        persistence_stage: Any,
        record: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> AuditRecordResult:
        persisted = persistence_stage.run(storage=storage, record=record)
        history.append(persisted)
        return AuditRecordResult(record=persisted)

@dataclass
class MemoryConsolidationPhaseResult:
    memory_events: list[dict[str, Any]]


class MemoryConsolidationPhase:
    """Own memory extraction/consolidation after final gate."""

    name = "memory_consolidation_phase"

    def run(self, *, ctx: Any, memory: Any, memory_gate: Any, role_memory: Any, extract_fn: Any) -> MemoryConsolidationPhaseResult:
        events: list[dict[str, Any]] = []
        if ctx.mode_adj["allow_memory_consolidation"] and ctx.accepted:
            extracted = extract_fn({"prompt_meta": ctx.prompt_meta, "policy_meta": ctx.policy_meta}, ctx.child_metrics)
            for mem in extracted:
                memory.auto_challenge_contradictions(mem["content"], mem["kind"])
                existing = memory.reinforce_candidate(mem["content"])
                if existing is None:
                    ce = memory.add_candidate(
                        content=mem["content"],
                        source=mem["source"],
                        kind=mem["kind"],
                        metadata=mem["metadata"],
                    )
                else:
                    ce = existing
                md, mr, mdiag = memory_gate.check(ce, memory.data["consolidated"])
                event = {"candidate_memory": ce, "decision": md, "reason": mr, "diagnostics": mdiag}
                if md == "GREEN":
                    if not memory.is_already_consolidated(ce["content"]):
                        event["consolidated"] = memory.add_consolidated(
                            ce, {"decision": md, "reason": mr, "diagnostics": mdiag}
                        )
                    memory.mark_candidate_status(ce["id"], "consolidated")
                elif md == "YELLOW":
                    memory.mark_candidate_status(ce["id"], "review")
                    memory.increment_review_count(ce["id"])
                else:
                    memory.mark_candidate_status(ce["id"], "rejected")
                events.append(event)
        ctx.memory_events = events
        ctx.verdicts.append(role_memory.evaluate(ctx.memory_events))
        return MemoryConsolidationPhaseResult(memory_events=events)

@dataclass
class PostRunReportResult:
    replay: dict[str, Any]
    critique: dict[str, Any]
    human: dict[str, Any]
    memory: dict[str, Any]
    path: tuple[str, str, dict[str, Any]]


@dataclass(frozen=True)
class HoldLogicPhaseInput:
    council_decision: str
    candidate: Any
    evaluation_stage: Any


@dataclass(frozen=True)
class HoldLogicPhaseOutput:
    hold_metrics: dict[str, Any] | None
    hold_resolved: bool
    council_accepted: bool
    trace_entry: dict[str, Any]


class HoldLogicPhase:
    """Resolve GREEN/YELLOW council outcomes through explicit hold policy input."""

    name = "hold_logic"
    input_type = HoldLogicPhaseInput
    required_keys = ("council_decision", "candidate", "evaluation_stage")

    def build_input(self, registry: ContextRegistry) -> HoldLogicPhaseInput:
        values = registry.require(self.required_keys)
        return HoldLogicPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: HoldLogicPhaseInput) -> HoldLogicPhaseOutput:
        hold_metrics = None
        hold_resolved = False
        council_accepted = False
        if phase_input.council_decision == "GREEN":
            council_accepted = True
        elif phase_input.council_decision == "YELLOW":
            hold_metrics = phase_input.evaluation_stage.run(
                agent=phase_input.candidate,
                mode="extended",
            ).metrics
            threshold = phase_input.candidate.policy["hold_policy"]["extended_eval_threshold"]
            if (hold_metrics["extended_accuracy"] >= threshold
                    and hold_metrics["suspicious_rate"] <= 0.20):
                council_accepted = True
                hold_resolved = True
        trace_entry = {
            "stage": "hold",
            "decision": "ACCEPT" if council_accepted else "HOLD",
            "reason": "hold_resolved" if hold_resolved else (
                "council_green" if council_accepted else "blocked"),
        }
        return HoldLogicPhaseOutput(
            hold_metrics=hold_metrics,
            hold_resolved=hold_resolved,
            council_accepted=council_accepted,
            trace_entry=trace_entry,
        )

    def run(self, phase_input: HoldLogicPhaseInput | None = None, **kwargs: Any) -> PhaseResult | HoldLogicPhaseOutput:
        if phase_input is None:
            return self.evaluate(HoldLogicPhaseInput(**kwargs))
        out = self.evaluate(phase_input)
        return PhaseResult(
            phase=self.name,
            decision="ACCEPT" if out.council_accepted else "HOLD",
            reason=out.trace_entry["reason"],
            diagnostics={"hold_metrics": out.hold_metrics, "hold_resolved": out.hold_resolved},
            patch={
                "hold_metrics": out.hold_metrics,
                "hold_resolved": out.hold_resolved,
                "council_accepted": out.council_accepted,
            },
            trace_entries=(out.trace_entry,),
        )


@dataclass(frozen=True)
class HumanReviewPhaseInput:
    iteration: int
    human_override: HumanOverrideLayer
    council_decision: str
    council_reasons: list[str]
    council_accepted: bool
    verdicts: list[Any]
    dissent_info: dict[str, Any]
    escalation_info: dict[str, Any]
    path_model: Any
    erosion_detector: Any
    truth_status: str
    governance_mode: str
    dgm_requirements: dict[str, Any]
    dgm_reason: str


@dataclass(frozen=True)
class HumanReviewPhaseOutput:
    council_decision: str
    council_accepted: bool
    override_record: dict[str, Any] | None


class HumanReviewPhase:
    """Apply bounded human review as a typed declarative phase."""

    name = "human_review"
    input_type = HumanReviewPhaseInput
    required_keys = (
        "iteration", "human_override", "council_decision", "council_reasons",
        "council_accepted", "verdicts", "dissent_info", "escalation_info",
        "path_model", "erosion_detector", "ts_d", "governance_mode",
        "dgm_requirements", "dgm_reason",
    )

    def build_input(self, registry: ContextRegistry) -> HumanReviewPhaseInput:
        values = registry.require(self.required_keys)
        return HumanReviewPhaseInput(
            iteration=values["iteration"],
            human_override=values["human_override"],
            council_decision=values["council_decision"],
            council_reasons=values["council_reasons"],
            council_accepted=values["council_accepted"],
            verdicts=values["verdicts"],
            dissent_info=values["dissent_info"],
            escalation_info=values["escalation_info"],
            path_model=values["path_model"],
            erosion_detector=values["erosion_detector"],
            truth_status=values["ts_d"],
            governance_mode=values["governance_mode"],
            dgm_requirements=values["dgm_requirements"],
            dgm_reason=values["dgm_reason"],
        )

    @staticmethod
    def evaluate(phase_input: HumanReviewPhaseInput) -> HumanReviewPhaseOutput:
        mandatory, trigger_reasons = phase_input.human_override.is_mandatory_review(
            phase_input.council_decision,
            phase_input.council_reasons,
            phase_input.verdicts,
            system_state={
                "path_status": phase_input.path_model.assess()[0],
                "dissent_count": len(phase_input.dissent_info.get("dissenters", [])),
                "erosion_status": phase_input.erosion_detector.check()[0],
                "truth_status": phase_input.truth_status,
            },
        )
        mandatory, trigger_reasons = require_human_review_from_dgm(
            mandatory, trigger_reasons, phase_input.dgm_requirements
        )
        council_decision = phase_input.council_decision
        council_accepted = phase_input.council_accepted
        override_record = None
        if mandatory or phase_input.escalation_info["escalation_requested"]:
            combined = trigger_reasons + phase_input.escalation_info.get("escalating_roles", [])
            human_system_state = {
                "path_status": phase_input.path_model.assess()[0],
                "dissent_count": len(phase_input.dissent_info.get("dissenters", [])),
                "erosion_status": phase_input.erosion_detector.check()[0],
                "truth_status": phase_input.truth_status,
            }
            decision_class = phase_input.human_override.classify_decision_class(
                council_decision=council_decision,
                trigger_reasons=combined,
                system_state=human_system_state,
                dgm_requirements=phase_input.dgm_requirements,
                dgm_reason=phase_input.dgm_reason,
            )
            hctx = {
                "iteration": phase_input.iteration,
                "council_decision": council_decision,
                "council_reasons": phase_input.council_reasons,
                "trigger_reasons": combined,
                "accepted_before_human": council_accepted,
                "mode": phase_input.governance_mode,
                "system_state": human_system_state,
                "dgm_requirements": phase_input.dgm_requirements,
                "dgm_reason": phase_input.dgm_reason,
                "decision_class": decision_class,
            }
            h_dec = phase_input.human_override.request_decision(hctx)
            final_d, final_a, applied = phase_input.human_override.override(
                council_decision,
                h_dec["action"],
                council_accepted,
                decision_class=decision_class,
                context=hctx,
            )
            if applied:
                council_decision = final_d
                council_accepted = final_a
            override_record = {
                "mandatory": mandatory,
                "trigger_reasons": combined,
                "action": h_dec["action"].value,
                "rationale": h_dec.get("rationale", ""),
                "decision_class": decision_class,
                "override_applied": applied,
            }
        return HumanReviewPhaseOutput(council_decision, council_accepted, override_record)

    def run(self, phase_input: HumanReviewPhaseInput | None = None, **kwargs: Any) -> PhaseResult | HumanReviewPhaseResult:
        if phase_input is None:
            out = self.evaluate(HumanReviewPhaseInput(**kwargs))
            return HumanReviewPhaseResult(out.council_decision, out.council_accepted, out.override_record)
        out = self.evaluate(phase_input)
        return PhaseResult(
            phase=self.name,
            decision=out.council_decision,
            reason=(out.override_record or {}).get("rationale", "human_review_evaluated"),
            diagnostics={"override_record": out.override_record},
            patch={
                "council_decision": out.council_decision,
                "council_accepted": out.council_accepted,
                "human_override_record": out.override_record,
            },
        )


@dataclass(frozen=True)
class FinalGatePhaseInput:
    extended_gate_stage: Any
    council_decision: str
    attractor: str
    trends: Any
    current_state: Any
    drel_status: str
    drel_reason: str
    drel_diagnostics: dict[str, Any]
    real_agency: float
    agency_diagnostics: dict[str, Any]
    sincerity_risk: float
    sincerity_diagnostics: dict[str, Any]
    external_reversibility_verified: bool
    external_openness: float
    external_diagnostics: dict[str, Any]
    dissent_independence: float
    dissent_visibility: float
    axiom_risk: float
    axiom_diagnostics: dict[str, Any]
    silence_risk: float
    silence_diagnostics: dict[str, Any]
    proxy_risk: float
    proxy_diagnostics: dict[str, Any]
    dgm_admissible: bool
    dgm_post_diagnostics: dict[str, Any]
    sham_risk: float
    sham_downgrade: bool
    sham_diagnostics: dict[str, Any]
    carrier_risk: float
    carrier_block: bool
    carrier_diagnostics: dict[str, Any]
    complexity_admissible: bool
    complexity_risk: float
    complexity_diagnostics: dict[str, Any]
    auxiliary: dict[str, Any]


@dataclass(frozen=True)
class FinalGatePhaseOutput:
    attractor: str
    decision: str
    reason: str
    diagnostics: dict[str, Any]
    trace_entry: dict[str, Any]


class FinalGatePhase:
    """Apply final extended gate with typed inputs and immutable patch output."""

    name = "final_gate"
    input_type = FinalGatePhaseInput
    required_keys = (
        "extended_gate_stage", "council_decision", "attractor", "trends", "curr_state",
        "drel_status", "drel_reason", "drel_diag", "real_agency", "agency_diag",
        "ss_risk", "ss_diag", "ext_rev_verified", "o_ext", "ext_int_diag",
        "ss_d_ind", "ss_d_vis", "axiom_risk", "axiom_diag", "silence_risk",
        "silence_diag", "proxy_risk", "proxy_diag", "dgm_admissible",
        "dgm_post_diag", "sham_risk", "sham_downgrade", "sham_diag",
        "carrier_risk", "carrier_block", "carrier_diag", "complexity_admissible",
        "complexity_risk", "complexity_diag", "auxiliary",
    )

    def build_input(self, registry: ContextRegistry) -> FinalGatePhaseInput:
        v = registry.require(self.required_keys)
        return FinalGatePhaseInput(
            extended_gate_stage=v["extended_gate_stage"],
            council_decision=v["council_decision"],
            attractor=v["attractor"],
            trends=v["trends"],
            current_state=v["curr_state"],
            drel_status=v["drel_status"],
            drel_reason=v["drel_reason"],
            drel_diagnostics=v["drel_diag"],
            real_agency=v["real_agency"],
            agency_diagnostics=v["agency_diag"],
            sincerity_risk=v["ss_risk"],
            sincerity_diagnostics=v["ss_diag"],
            external_reversibility_verified=v["ext_rev_verified"],
            external_openness=v["o_ext"],
            external_diagnostics=v["ext_int_diag"],
            dissent_independence=v["ss_d_ind"],
            dissent_visibility=v["ss_d_vis"],
            axiom_risk=v["axiom_risk"],
            axiom_diagnostics=v["axiom_diag"],
            silence_risk=v["silence_risk"],
            silence_diagnostics=v["silence_diag"],
            proxy_risk=v["proxy_risk"],
            proxy_diagnostics=v["proxy_diag"],
            dgm_admissible=v["dgm_admissible"],
            dgm_post_diagnostics=v["dgm_post_diag"],
            sham_risk=v["sham_risk"],
            sham_downgrade=v["sham_downgrade"],
            sham_diagnostics=v["sham_diag"],
            carrier_risk=v["carrier_risk"],
            carrier_block=v["carrier_block"],
            carrier_diagnostics=v["carrier_diag"],
            complexity_admissible=v["complexity_admissible"],
            complexity_risk=v["complexity_risk"],
            complexity_diagnostics=v["complexity_diag"],
            auxiliary=v["auxiliary"],
        )

    @staticmethod
    def evaluate(phase_input: FinalGatePhaseInput) -> FinalGatePhaseOutput:
        attractor = phase_input.attractor
        current_state = phase_input.current_state
        if phase_input.sham_downgrade:
            attractor = "UNCERTAIN"
            # Keep the legacy extended-gate semantics, but make the resulting
            # attractor an explicit patch rather than relying on hidden context
            # mutation as the only carrier.
            current_state.attractor = attractor
        ext_out = phase_input.extended_gate_stage.run(
            council_decision=phase_input.council_decision,
            attractor=attractor,
            trends=phase_input.trends,
            current_state=current_state,
        )
        decision = ext_out.decision
        reason = ext_out.reason
        diagnostics = dict(ext_out.diagnostics)
        if phase_input.drel_status == "RED" and decision == "GO":
            decision = "STOP"
            reason = f"drel_block:{phase_input.drel_reason}"
        elif phase_input.drel_status == "YELLOW" and decision == "GO":
            decision = "HOLD"
            reason = f"drel_caution:{phase_input.drel_reason}"
        if phase_input.real_agency < 0.40 and decision == "GO":
            decision = "HOLD"
            reason = f"agency_insufficient:{phase_input.real_agency:.2f}"
        if decision == "GO":
            if phase_input.sincerity_risk >= 0.65:
                decision = "HOLD"; reason = f"a3_sincerity_block:{phase_input.sincerity_risk:.3f}"
            elif not phase_input.external_reversibility_verified:
                decision = "HOLD"; reason = "a3_external_reversibility_not_verified"
            elif phase_input.external_openness < 0.40:
                decision = "HOLD"; reason = f"a3_o_external_low:{phase_input.external_openness:.3f}"
            elif phase_input.dissent_independence < 0.35 and phase_input.dissent_visibility > 0.3:
                decision = "HOLD"; reason = f"a3_dissent_not_independent:{phase_input.dissent_independence:.3f}"
            elif phase_input.axiom_risk >= 0.60:
                decision = "HOLD"; reason = f"a4_axiom_conflict:{phase_input.axiom_risk:.3f}"
            elif phase_input.silence_risk >= 0.60:
                decision = "HOLD"; reason = f"a4_silence_risk:{phase_input.silence_risk:.3f}"
            elif phase_input.proxy_risk >= 0.60:
                decision = "HOLD"; reason = f"a4_proxy_integrity:{phase_input.proxy_risk:.3f}"
            elif not phase_input.dgm_admissible:
                decision = "HOLD"; reason = f"v8_pareto_inadmissible:{phase_input.dgm_post_diagnostics.get('violations', [])}"
            elif phase_input.sham_risk >= SHAM_RESONANCE_BLOCK:
                decision = "HOLD"; reason = f"v9_sham_resonance:{phase_input.sham_risk:.3f}"
            elif phase_input.carrier_block:
                decision = "HOLD"; reason = f"v9_carrier_erosion:{phase_input.carrier_risk:.3f}"
            elif not phase_input.complexity_admissible:
                decision = "HOLD"
                reason = f"v9_complexity_inadmissible:risk={phase_input.complexity_risk:.3f} pattern={phase_input.complexity_diagnostics.get('pattern')}"
        diagnostics.update({
            "drel": phase_input.drel_diagnostics,
            "agency": phase_input.agency_diagnostics,
            "a3_sincerity": phase_input.sincerity_diagnostics,
            "a3_external": phase_input.external_diagnostics,
            "a4_axiom": phase_input.axiom_diagnostics,
            "a4_silence": phase_input.silence_diagnostics,
            "a4_proxy": phase_input.proxy_diagnostics,
            "v8_pareto": phase_input.dgm_post_diagnostics,
            "v9_sham_resonance": phase_input.sham_diagnostics,
            "v9_carrier_erosion": phase_input.carrier_diagnostics,
            "v9_complexity_admissibility": phase_input.complexity_diagnostics,
            "v9_auxiliary_indicators": phase_input.auxiliary,
        })
        trace_entry = {"stage": "extended", "decision": decision, "reason": reason}
        return FinalGatePhaseOutput(attractor, decision, reason, diagnostics, trace_entry)

    def run(self, phase_input: FinalGatePhaseInput | None = None, **kwargs: Any) -> PhaseResult | FinalGatePhaseResult:
        if phase_input is None:
            out = self.evaluate(FinalGatePhaseInput(**kwargs))
            return FinalGatePhaseResult(out.attractor, out.decision, out.reason, out.diagnostics)
        out = self.evaluate(phase_input)
        return PhaseResult(
            phase=self.name,
            decision=out.decision,
            reason=out.reason,
            diagnostics=out.diagnostics,
            patch={"attractor": out.attractor, "ext_decision": out.decision, "ext_reason": out.reason, "ext_diag": out.diagnostics},
            trace_entries=(out.trace_entry,),
        )


@dataclass(frozen=True)
class PersistencePhaseInput:
    ctx: Any
    build_snapshot_fn: Any
    build_record_fn: Any
    storage: Any
    persistence_stage: Any
    audit_recorder: Any
    history: list[dict[str, Any]]
    snapshots: list[dict[str, Any]]
    evidence_generator: Any
    shadow_recorder: Any
    baseline_metrics: dict[str, Any]
    governance_mode: str


class PersistencePhase:
    """Build and persist the final iteration audit record as a declarative phase."""

    name = "persist_iteration_record"
    input_type = PersistencePhaseInput
    required_keys = (
        "ctx", "build_snapshot_fn", "build_record_fn", "storage", "persistence_stage",
        "audit_recorder", "history", "snapshots", "evidence_generator", "shadow_recorder",
        "baseline_metrics", "governance_mode",
    )

    def build_input(self, registry: ContextRegistry) -> PersistencePhaseInput:
        values = registry.require(self.required_keys)
        return PersistencePhaseInput(**values)

    def run(self, phase_input: PersistencePhaseInput) -> PhaseResult:
        ctx = phase_input.ctx
        snapshot = phase_input.build_snapshot_fn(
            iteration=ctx.iteration,
            parent_metrics=ctx.parent_metrics,
            child_metrics=ctx.child_metrics,
            baseline_metrics=phase_input.baseline_metrics,
            parent_policy=ctx.previous_policy,
            child_policy=ctx.candidate.policy,
            mode=phase_input.governance_mode,
            mode_adjustments=ctx.mode_adj,
            council_decision=ctx.council_decision,
            council_reasons=ctx.council_reasons,
            per_role=ctx.per_role,
            erosion_state=ctx.erosion_status,
            human_decision=ctx.human_override_record,
        )
        phase_input.snapshots.append(snapshot)
        evidence_bundle = ctx.evidence_bundle
        if ctx.final_decision in {"HOLD", "STOP", "ROLLBACK", "RED"} or ctx.council_decision in {"RED", "YELLOW"}:
            evidence_bundle = phase_input.evidence_generator.generate(ctx).to_dict()
        raw_record = phase_input.build_record_fn(ctx)
        raw_record["evidence_bundle"] = evidence_bundle
        shadow_observation = None
        if phase_input.shadow_recorder is not None:
            from calibration import ShadowDecision
            shadow = ShadowDecision(
                run_id="pending-until-persisted",
                iteration=ctx.iteration,
                gate_decision=ctx.council_decision,
                final_decision=ctx.final_decision,
                human_decision=(ctx.human_override_record or {}).get("action", "not_reviewed"),
                thresholds=ctx.adjusted,
                diagnostics={"extended_gate": ctx.ext_diag, "semantic_drift": ctx.semantic_drift},
            )
            shadow_observation = shadow.to_dict()
            raw_record["shadow_observation"] = shadow_observation
        # Include the persistence phase audit event in the hash-protected record.
        preliminary = PhaseResult(
            phase=self.name,
            decision="PERSISTED",
            reason="audit_record_persisted",
            diagnostics={"iteration": ctx.iteration, "record_kind": "iteration"},
            patch={"record": "<persisted>", "snapshot": "<snapshot>"},
            audit_already_in_patch=True,
        )
        persistence_audit_entry = preliminary.audit_entry(iteration=ctx.iteration)
        if getattr(ctx, "trace_id", None):
            persistence_audit_entry["trace_id"] = ctx.trace_id
        raw_record["phase_audit"] = list(raw_record.get("phase_audit", [])) + [
            persistence_audit_entry
        ]
        persistence_event = RuntimeEvent.from_phase_result(
            result=preliminary,
            iteration=ctx.iteration,
            trace_id=getattr(ctx, "trace_id", None),
            stream_id=f"iteration-{ctx.iteration}",
        ).to_dict()
        raw_record["events_v12"] = list(raw_record.get("events_v12", [])) + [persistence_event]
        persisted = phase_input.audit_recorder.persist(
            storage=phase_input.storage,
            persistence_stage=phase_input.persistence_stage,
            record=raw_record,
            history=phase_input.history,
        ).record
        if phase_input.shadow_recorder is not None and shadow_observation is not None:
            shadow_observation["run_id"] = persisted.get("run_id", "unknown")
            phase_input.shadow_recorder.append(ShadowDecision(**shadow_observation))
        final_phase_audit = persisted.get("phase_audit", raw_record["phase_audit"])
        return PhaseResult(
            phase=self.name,
            decision="PERSISTED",
            reason="audit_record_persisted",
            diagnostics={"record_hash": persisted.get("record_hash"), "phase_audit_count": len(final_phase_audit)},
            patch={
                "snapshot": snapshot,
                "evidence_bundle": evidence_bundle,
                "shadow_observation": shadow_observation,
                "record": persisted,
                "phase_audit": final_phase_audit,
            },
            audit_already_in_patch=True,
        )


@dataclass(frozen=True)
class PostRunReporterInput:
    replay_engine: Any
    snapshots: list[dict[str, Any]]
    post_hoc_critic: Any
    records: list[dict[str, Any]]
    human_override: Any
    memory: Any
    path_model: Any
    effective_attractor_state: Any
    prev_attractor_state: Any
    logger: Any


class PostRunReporter:
    """Create structured post-run summary with explicit input contract."""

    name = "post_run_reporter"
    input_type = PostRunReporterInput
    required_keys = (
        "replay_engine", "snapshots", "post_hoc_critic", "records", "human_override",
        "memory", "path_model", "effective_attractor_state", "prev_attractor_state", "logger",
    )

    def build_input(self, registry: ContextRegistry) -> PostRunReporterInput:
        return PostRunReporterInput(**registry.require(self.required_keys))

    def run(self, phase_input: PostRunReporterInput | None = None, **kwargs: Any) -> PhaseResult | PostRunReportResult:
        if phase_input is None:
            phase_input = PostRunReporterInput(**kwargs)
            legacy = True
        else:
            legacy = False
        replay_results = phase_input.replay_engine.replay_all(phase_input.snapshots)
        critique = phase_input.post_hoc_critic.critique_sequence(phase_input.records)
        ho_stats = phase_input.human_override.get_intervention_stats()
        memory_stats = phase_input.memory.lifecycle_stats()
        path_assessment = phase_input.path_model.assess()
        phase_input.logger.info("\n── Post-Run Analysis ──────────────────────────────────────")
        phase_input.logger.info("Replay: %s/%s (%.0f%%)", replay_results["matches"], replay_results["total"], replay_results["match_rate"] * 100)
        phase_input.logger.info("Post-hoc: severity=%s, %s findings", critique["severity"], len(critique["findings"]))
        for finding in critique["findings"]:
            phase_input.logger.info("  [%s] %s: %s", finding["severity"], finding["type"], finding["detail"])
        phase_input.logger.info("Human: %s interventions, %s overrides", ho_stats["total"], ho_stats.get("overrides", 0))
        phase_input.logger.info("Memory: %s", memory_stats)
        phase_input.logger.info("Path: %s — %s", path_assessment[0], path_assessment[1])
        if phase_input.effective_attractor_state:
            s = phase_input.effective_attractor_state
            phase_input.logger.info("\nEffective system state: Σ=%.3f L=%.3f O=%.3f D=%.3f → %s", s.sigma, s.l, s.o, s.d, s.attractor)
        else:
            phase_input.logger.info("\nEffective system state: unchanged (no candidate was accepted)")
        if phase_input.prev_attractor_state and phase_input.prev_attractor_state is not phase_input.effective_attractor_state:
            s = phase_input.prev_attractor_state
            phase_input.logger.info("Last evaluated candidate: Σ=%.3f L=%.3f O=%.3f D=%.3f → %s (rejected)", s.sigma, s.l, s.o, s.d, s.attractor)
        report = PostRunReportResult(
            replay=replay_results,
            critique=critique,
            human=ho_stats,
            memory=memory_stats,
            path=path_assessment,
        )
        if legacy:
            return report
        return PhaseResult(
            phase=self.name,
            decision="REPORTED",
            reason="post_run_summary_generated",
            diagnostics={"replay": replay_results, "critique": critique, "human": ho_stats, "memory": memory_stats},
            patch={"post_run_report": report},
        )
