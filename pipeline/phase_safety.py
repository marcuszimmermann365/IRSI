"""Attractor and adversarial diagnostic phase services.

P1 split from the former monolithic ``pipeline.phase_services`` module.
"""

from dataclasses import asdict, dataclass
from typing import Any

from pipeline.phase_runtime import ContextRegistry, PhaseResult


def _compact_history(records: list[dict[str, Any]], *, window: int = 5) -> list[dict[str, Any]]:
    """Return only the recent, diagnostic-relevant trajectory fields.

    Several adversarial diagnostics need short history trajectories, but passing
    complete materialized records back into runtime context causes recursive audit
    growth (records -> events -> patches -> history -> records).  Keep the values
    those diagnostics actually inspect and bind each source record by hash.
    """
    compact: list[dict[str, Any]] = []
    for record in list(records or [])[-window:]:
        if not isinstance(record, dict):
            continue
        human_coupling = record.get("human_coupling")
        if isinstance(human_coupling, dict) and "diagnostics" in human_coupling:
            # Preserve both shapes used by carrier/deception helpers.
            diagnostics = human_coupling.get("diagnostics") or {}
            if isinstance(diagnostics, dict):
                human_coupling = {**diagnostics, "diagnostics": diagnostics}
        compact.append({
            "iteration": record.get("iteration"),
            "record_hash": record.get("record_hash"),
            "final_decision": record.get("final_decision"),
            "accepted": record.get("accepted"),
            "human_override": record.get("human_override"),
            "human_coupling": human_coupling,
            "memory_events": record.get("memory_events", []),
            "attractor_state": record.get("attractor_state"),
            "semantic_drift": record.get("semantic_drift"),
        })
    return compact


def _history_ref(records: list[dict[str, Any]], *, window: int = 5) -> dict[str, Any]:
    recent = [r for r in list(records or [])[-window:] if isinstance(r, dict)]
    return {
        "total_records": len(records or []),
        "window": window,
        "recent_record_hashes": [r.get("record_hash") for r in recent if r.get("record_hash")],
        "recent_iterations": [r.get("iteration") for r in recent if r.get("iteration") is not None],
    }


@dataclass(frozen=True)
class AttractorPhaseInput:
    child_metrics: dict[str, Any]
    human_coupling_diagnostics: dict[str, Any]
    per_role: dict[str, Any]
    memory_lifecycle: dict[str, Any]
    truth_diagnostics: dict[str, Any]
    counter_decision: str
    counter_reasons: list[str]
    counter_diagnostics: dict[str, Any]
    human_override_record: dict[str, Any] | None
    dissent_info: dict[str, Any]
    path_diagnostics: dict[str, Any]
    gate_diagnostics: dict[str, Any]
    erosion_diagnostics: dict[str, Any]
    history: list[dict[str, Any]]
    build_state_fn: Any
    attractor_stage: Any
    effective_attractor_state: Any
    baseline_attractor_state: Any
    previous_candidate_state: Any


@dataclass(frozen=True)
class AttractorDiagnosticsOutput:
    current_state: Any
    attractor: str
    trends: Any
    confidence: float
    gating_anchor: Any
    gating_anchor_source: str
    candidate_diagnostics: dict[str, Any] | None
    sigma: float
    l_value: float
    o_value: float
    d_value: float
    sigma_components: dict[str, Any]
    l_components: dict[str, Any]
    o_components: dict[str, Any]
    d_components: dict[str, Any]

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "attractor": self.attractor,
            "confidence": self.confidence,
            "gating_anchor_source": self.gating_anchor_source,
            "candidate_diagnostics": self.candidate_diagnostics,
            "sigma": self.sigma,
            "l_value": self.l_value,
            "o_value": self.o_value,
            "d_value": self.d_value,
            "sigma_components": self.sigma_components,
            "l_components": self.l_components,
            "o_components": self.o_components,
            "d_components": self.d_components,
            "trends": self.trends.to_dict() if self.trends else None,
        }


class AttractorPhase:
    """Compute attractor diagnostics via explicit input and immutable result."""

    name = "attractor_phase"
    input_type = AttractorPhaseInput
    required_keys = (
        "child_metrics", "hc_diag", "per_role", "memory", "ts_diag",
        "cc_final", "cc_reasons", "cc_diag", "human_override_record",
        "dissent_info", "path_diag", "gate_diag", "erosion_diag",
        "history", "build_state_fn", "attractor_stage", "effective_attractor_state",
        "baseline_attractor_state", "prev_attractor_state",
    )

    def build_input(self, registry: ContextRegistry) -> AttractorPhaseInput:
        values = registry.require(self.required_keys)
        return AttractorPhaseInput(
            child_metrics=values["child_metrics"],
            human_coupling_diagnostics=values["hc_diag"],
            per_role=values["per_role"],
            memory_lifecycle=values["memory"].lifecycle_stats(),
            truth_diagnostics=values["ts_diag"],
            counter_decision=values["cc_final"],
            counter_reasons=values["cc_reasons"],
            counter_diagnostics=values["cc_diag"],
            human_override_record=values["human_override_record"],
            dissent_info=values["dissent_info"],
            path_diagnostics=values["path_diag"],
            gate_diagnostics=values["gate_diag"],
            erosion_diagnostics=values["erosion_diag"],
            history=values["history"],
            build_state_fn=values["build_state_fn"],
            attractor_stage=values["attractor_stage"],
            effective_attractor_state=values["effective_attractor_state"],
            baseline_attractor_state=values["baseline_attractor_state"],
            previous_candidate_state=values["prev_attractor_state"],
        )

    @staticmethod
    def evaluate(phase_input: AttractorPhaseInput) -> AttractorDiagnosticsOutput:
        attractor_context = {
            "metrics": phase_input.child_metrics,
            "human_coupling": phase_input.human_coupling_diagnostics,
            "roles_state": phase_input.per_role,
            "memory_state": phase_input.memory_lifecycle,
            "replay_consistency": 1.0,
            "truth_diag": phase_input.truth_diagnostics,
            "counter_check": {
                "decision": phase_input.counter_decision,
                "reasons": phase_input.counter_reasons,
                "diagnostics": phase_input.counter_diagnostics,
            },
            "human_override": phase_input.human_override_record,
            "dissent": phase_input.dissent_info,
            "council_per_role": phase_input.per_role,
            "path_diag": phase_input.path_diagnostics,
            "gate_diag": phase_input.gate_diagnostics,
            "erosion_diag": phase_input.erosion_diagnostics,
            "history": phase_input.history,
        }
        out = phase_input.attractor_stage.run(
            build_state_fn=phase_input.build_state_fn,
            metrics=phase_input.child_metrics,
            history=phase_input.history,
            context=attractor_context,
            effective_attractor_state=phase_input.effective_attractor_state,
            baseline_attractor_state=phase_input.baseline_attractor_state,
            previous_candidate_state=phase_input.previous_candidate_state,
        )
        curr = out.current_state
        return AttractorDiagnosticsOutput(
            current_state=curr,
            attractor=out.attractor,
            trends=out.trends,
            confidence=out.confidence,
            gating_anchor=out.gating_anchor,
            gating_anchor_source=out.gating_anchor_source,
            candidate_diagnostics=out.candidate_diagnostics,
            sigma=curr.sigma,
            l_value=curr.l,
            o_value=curr.o,
            d_value=curr.d,
            sigma_components=curr.sigma_components,
            l_components=curr.l_components,
            o_components=curr.o_components,
            d_components=curr.d_components,
        )

    def run(self, phase_input: AttractorPhaseInput | None = None, **kwargs: Any) -> PhaseResult | AttractorDiagnosticsOutput:
        # Legacy keyword compatibility for older direct callers.
        if phase_input is None:
            if "ctx" in kwargs:
                ctx = kwargs["ctx"]
                phase_input = AttractorPhaseInput(
                    child_metrics=ctx.child_metrics,
                    human_coupling_diagnostics=ctx.hc_diag,
                    per_role=ctx.per_role,
                    memory_lifecycle=kwargs["memory"].lifecycle_stats(),
                    truth_diagnostics=ctx.ts_diag,
                    counter_decision=ctx.cc_final,
                    counter_reasons=ctx.cc_reasons,
                    counter_diagnostics=ctx.cc_diag,
                    human_override_record=ctx.human_override_record,
                    dissent_info=ctx.dissent_info,
                    path_diagnostics=ctx.path_diag,
                    gate_diagnostics=ctx.gate_diag,
                    erosion_diagnostics=ctx.erosion_diag,
                    history=kwargs["history"],
                    build_state_fn=kwargs["build_state_fn"],
                    attractor_stage=kwargs["attractor_stage"],
                    effective_attractor_state=kwargs["effective_attractor_state"],
                    baseline_attractor_state=kwargs["baseline_attractor_state"],
                    previous_candidate_state=kwargs["prev_attractor_state"],
                )
            else:
                phase_input = AttractorPhaseInput(**kwargs)
            return self.evaluate(phase_input)

        out = self.evaluate(phase_input)
        trace_entries = [{
            "stage": "attractor",
            "decision": out.attractor,
            "reason": f"Σ={out.sigma:.3f} L={out.l_value:.3f} O={out.o_value:.3f} D={out.d_value:.3f} anchor={out.gating_anchor_source}",
        }]
        if out.candidate_diagnostics:
            trace_entries.append({
                "stage": "attractor_candidate_diagnostic",
                "decision": "DIAGNOSTIC",
                "reason": f"vs_rejected_candidate: attr={out.candidate_diagnostics['attractor']} (NOT gating-relevant)",
            })
        return PhaseResult(
            phase=self.name,
            decision=out.attractor,
            reason=f"anchor={out.gating_anchor_source}; confidence={out.confidence:.3f}",
            diagnostics=out.to_diagnostics(),
            patch={
                "curr_state": out.current_state,
                "attractor": out.attractor,
                "trends": out.trends,
                "confidence": out.confidence,
                "gating_anchor": out.gating_anchor,
                "gating_anchor_source": out.gating_anchor_source,
                "candidate_diagnostics": out.candidate_diagnostics,
                "sigma": out.sigma,
                "l_val": out.l_value,
                "o_val": out.o_value,
                "d_val": out.d_value,
                "sigma_comp": out.sigma_components,
                "l_comp": out.l_components,
                "o_comp": out.o_components,
                "d_comp": out.d_components,
                "attractor_diagnostics": out.to_diagnostics(),
            },
            trace_entries=tuple(trace_entries),
        )


@dataclass(frozen=True)
class DRELDiagnosticOutput:
    status: str
    reason: str
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class A3DiagnosticOutput:
    sincerity_risk: float
    dissent_visibility: float
    dissent_independence: float
    sincerity_diagnostics: dict[str, Any]
    external_openness: float
    combined_openness: float
    external_diagnostics: dict[str, Any]
    external_reversibility_verified: bool
    resonance_eligible: bool
    resonance_reason: str


@dataclass(frozen=True)
class A4DiagnosticOutput:
    axiom_risk: float
    axiom_diagnostics: dict[str, Any]
    silence_risk: float
    silence_diagnostics: dict[str, Any]
    proxy_risk: float
    proxy_diagnostics: dict[str, Any]
    max_risk: float


@dataclass(frozen=True)
class AgencyDiagnosticOutput:
    real_agency: float
    manipulation_risk: float
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class ParetoDiagnosticOutput:
    admissible: bool
    quality: dict[str, Any]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class ShamResonanceOutput:
    risk: float
    downgrade: bool
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class CarrierErosionOutput:
    risk: float
    block: bool
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class ComplexityAdmissibilityOutput:
    admissible: bool
    risk: float
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class AuxiliaryIndicatorsOutput:
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class AdversarialPhaseInput:
    iteration: int
    parent_metrics: dict[str, Any]
    child_metrics: dict[str, Any]
    policy_meta: dict[str, Any]
    prompt_meta: dict[str, Any]
    gate_diag: dict[str, Any]
    truth_diag: dict[str, Any]
    erosion_diag: dict[str, Any]
    path_diag: dict[str, Any]
    counter_decision: str
    counter_reasons: list[str]
    counter_diagnostics: dict[str, Any]
    human_coupling_diagnostics: dict[str, Any]
    human_override_record: dict[str, Any] | None
    dissent_info: dict[str, Any]
    per_role: dict[str, Any]
    history: list[dict[str, Any]]
    decision_trace_length_before: int
    hold_metrics: dict[str, Any] | None
    o_value: float
    curr_state: Any
    attractor: str
    dgm_proposal: Any
    previous_attractor_state: Any
    sigma: float
    a3_stage: Any
    a4_stage: Any
    drel_stage: Any
    external_commits: Any
    agency_verifier: Any
    dgm_bridge: Any


@dataclass(frozen=True)
class AdversarialDiagnosticsOutput:
    drel_context: dict[str, Any]
    drel: DRELDiagnosticOutput
    a3: A3DiagnosticOutput
    agency: AgencyDiagnosticOutput
    a4: A4DiagnosticOutput
    pareto: ParetoDiagnosticOutput
    sham_resonance: ShamResonanceOutput
    carrier_erosion: CarrierErosionOutput
    complexity: ComplexityAdmissibilityOutput
    auxiliary: AuxiliaryIndicatorsOutput
    trace_entries: tuple[dict[str, Any], ...]
    llm_error_rate: float

    @property
    def drel_status(self) -> str:
        return self.drel.status

    @property
    def drel_reason(self) -> str:
        return self.drel.reason

    @property
    def drel_diagnostics(self) -> dict[str, Any]:
        return self.drel.diagnostics

    @property
    def dgm_admissible(self) -> bool:
        return self.pareto.admissible

    @property
    def dgm_post_diagnostics(self) -> dict[str, Any]:
        return self.pareto.diagnostics

    @property
    def max_a4_risk(self) -> float:
        return self.a4.max_risk

    @property
    def a3_sincerity_risk(self) -> float:
        return self.a3.sincerity_risk

    @property
    def a4_diagnostics(self) -> dict[str, Any]:
        return {
            "axiom": self.a4.axiom_diagnostics,
            "silence": self.a4.silence_diagnostics,
            "proxy": self.a4.proxy_diagnostics,
        }

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.drel.status == "RED":
            blockers.append(f"drel:{self.drel.reason}")
        if self.a3.sincerity_risk >= 0.65:
            blockers.append(f"a3_sincerity:{self.a3.sincerity_risk:.3f}")
        if self.a4.max_risk >= 0.60:
            blockers.append(f"a4:{self.a4.max_risk:.3f}")
        if not self.pareto.admissible:
            blockers.append("pareto_inadmissible")
        if self.sham_resonance.downgrade:
            blockers.append("sham_resonance_downgrade")
        if self.carrier_erosion.block:
            blockers.append("carrier_erosion_block")
        if not self.complexity.admissible:
            blockers.append("complexity_inadmissible")
        return tuple(blockers)

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if self.drel.status == "YELLOW":
            warnings.append(f"drel:{self.drel.reason}")
        if 0.40 <= self.a3.sincerity_risk < 0.65:
            warnings.append(f"a3_sincerity:{self.a3.sincerity_risk:.3f}")
        if 0.35 <= self.a4.max_risk < 0.60:
            warnings.append(f"a4:{self.a4.max_risk:.3f}")
        if self.sham_resonance.risk >= 0.30 and not self.sham_resonance.downgrade:
            warnings.append(f"sham_resonance:{self.sham_resonance.risk:.3f}")
        if self.carrier_erosion.risk >= 0.35 and not self.carrier_erosion.block:
            warnings.append(f"carrier_erosion:{self.carrier_erosion.risk:.3f}")
        if self.complexity.admissible and self.complexity.risk >= 0.30:
            warnings.append(f"complexity:{self.complexity.risk:.3f}")
        return tuple(warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drel": asdict(self.drel),
            "a3": asdict(self.a3),
            "agency": asdict(self.agency),
            "a4": asdict(self.a4),
            "pareto": asdict(self.pareto),
            "sham_resonance": asdict(self.sham_resonance),
            "carrier_erosion": asdict(self.carrier_erosion),
            "complexity": asdict(self.complexity),
            "auxiliary": asdict(self.auxiliary),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "llm_error_rate": self.llm_error_rate,
        }

    def apply_to(self, ctx: Any) -> Any:
        """Legacy helper for callers that still expect result.apply_to(ctx)."""
        patch = AdversarialPhase._patch_from_output(self)
        for key, value in patch.items():
            setattr(ctx, key, value)
        ctx.decision_trace = list(ctx.decision_trace) + [dict(e) for e in self.trace_entries]
        return ctx


# Backwards-compatible alias with the V11.0 name, now carrying nested typed
# diagnostics rather than a flat bag of updates only.
AdversarialPhaseResult = AdversarialDiagnosticsOutput


class AdversarialPhase:
    """Run typed nested safety diagnostics as a declarative phase."""

    name = "adversarial_phase"
    input_type = AdversarialPhaseInput
    required_keys = (
        "iteration", "parent_metrics", "child_metrics", "policy_meta", "prompt_meta",
        "gate_diag", "ts_diag", "erosion_diag", "path_diag", "cc_final",
        "cc_reasons", "cc_diag", "hc_diag", "human_override_record", "dissent_info",
        "per_role", "history", "decision_trace", "hold_metrics", "o_val",
        "curr_state", "attractor", "dgm_proposal", "prev_attractor_state", "sigma",
        "a3_stage", "a4_stage", "drel_stage", "external_commits", "agency_verifier",
        "dgm_bridge",
    )

    def build_input(self, registry: ContextRegistry) -> AdversarialPhaseInput:
        v = registry.require(self.required_keys)
        return AdversarialPhaseInput(
            iteration=v["iteration"],
            parent_metrics=v["parent_metrics"],
            child_metrics=v["child_metrics"],
            policy_meta=v["policy_meta"],
            prompt_meta=v["prompt_meta"],
            gate_diag=v["gate_diag"],
            truth_diag=v["ts_diag"],
            erosion_diag=v["erosion_diag"],
            path_diag=v["path_diag"],
            counter_decision=v["cc_final"],
            counter_reasons=v["cc_reasons"],
            counter_diagnostics=v["cc_diag"],
            human_coupling_diagnostics=v["hc_diag"],
            human_override_record=v["human_override_record"],
            dissent_info=v["dissent_info"],
            per_role=v["per_role"],
            history=v["history"],
            decision_trace_length_before=len(v["decision_trace"]),
            hold_metrics=v["hold_metrics"],
            o_value=v["o_val"],
            curr_state=v["curr_state"],
            attractor=v["attractor"],
            dgm_proposal=v["dgm_proposal"],
            previous_attractor_state=v["prev_attractor_state"],
            sigma=v["sigma"],
            a3_stage=v["a3_stage"],
            a4_stage=v["a4_stage"],
            drel_stage=v["drel_stage"],
            external_commits=v["external_commits"],
            agency_verifier=v["agency_verifier"],
            dgm_bridge=v["dgm_bridge"],
        )

    @staticmethod
    def evaluate(phase_input: AdversarialPhaseInput) -> AdversarialDiagnosticsOutput:
        from auxiliary_indicators import compute_auxiliary_indicators
        from axiom_conflict import compute_axiom_conflict_risk
        from carrier_erosion import compute_carrier_erosion
        from deception_surface import compute_deception_surface
        from external_integrity import check_resonance_eligibility, compute_cross_domain_openness
        from pareto_admissibility import check_complexity_admissibility
        from proxy_integrity import compute_proxy_integrity
        from sham_resonance import compute_sham_resonance
        from silence_monitor import compute_silence_risk
        from synthetic_sincerity import compute_synthetic_sincerity

        diagnostic_history = _compact_history(phase_input.history)
        drel_context: dict[str, Any] = {
            "metrics": phase_input.child_metrics,
            "policy_mutation": phase_input.policy_meta,
            "prompt_mutation": phase_input.prompt_meta,
            "parent_metrics": phase_input.parent_metrics,
            "child_metrics": phase_input.child_metrics,
            "gate_diag": phase_input.gate_diag,
            "gate_diagnostics": phase_input.gate_diag,
            "truth_diag": phase_input.truth_diag,
            "erosion_diag": phase_input.erosion_diag,
            "path_diag": phase_input.path_diag,
            "counter_check": {
                "decision": phase_input.counter_decision,
                "reasons": phase_input.counter_reasons,
                "diagnostics": phase_input.counter_diagnostics,
            },
            "human_coupling": phase_input.human_coupling_diagnostics,
            "human_override": phase_input.human_override_record,
            "dissent": phase_input.dissent_info,
            "council_per_role": phase_input.per_role,
            "council": phase_input.per_role,
            "history": diagnostic_history,
            "history_ref": _history_ref(phase_input.history),
            "decision_trace": [],
            "hold_metrics": phase_input.hold_metrics,
            "reflection": None,
            "memory_events": [],
        }

        a3_raw = phase_input.a3_stage.run(
            sincerity_fn=compute_synthetic_sincerity,
            external_fn=compute_cross_domain_openness,
            resonance_fn=check_resonance_eligibility,
            context=drel_context,
            o_value=phase_input.o_value,
            external_commits=phase_input.external_commits,
            iteration=phase_input.iteration,
        )
        a3 = A3DiagnosticOutput(
            sincerity_risk=a3_raw.sincerity_risk,
            dissent_visibility=a3_raw.dissent_visibility,
            dissent_independence=a3_raw.dissent_independence,
            sincerity_diagnostics=a3_raw.sincerity_diagnostics,
            external_openness=a3_raw.external_openness,
            combined_openness=a3_raw.combined_openness,
            external_diagnostics=a3_raw.external_diagnostics,
            external_reversibility_verified=a3_raw.external_reversibility_verified,
            resonance_eligible=a3_raw.resonance_ok,
            resonance_reason=a3_raw.resonance_reason,
        )
        drel_context["sincerity_diagnostics"] = a3.sincerity_diagnostics
        drel_context["external_integrity"] = a3.external_diagnostics
        drel_context["o_external"] = a3.external_openness
        drel_context["o_combined"] = a3.combined_openness

        drel_raw = phase_input.drel_stage.run(compute_fn=compute_deception_surface, context=drel_context)
        drel = DRELDiagnosticOutput(drel_raw.status, drel_raw.reason, drel_raw.diagnostics)
        real_agency, manipulation_risk, agency_diag = phase_input.agency_verifier.verify(drel_context)
        agency = AgencyDiagnosticOutput(real_agency, manipulation_risk, agency_diag)

        a4_raw = phase_input.a4_stage.run(
            axiom_fn=compute_axiom_conflict_risk,
            silence_fn=compute_silence_risk,
            proxy_fn=compute_proxy_integrity,
            context=drel_context,
        )
        a4 = A4DiagnosticOutput(
            axiom_risk=a4_raw.axiom_risk,
            axiom_diagnostics=a4_raw.axiom_diagnostics,
            silence_risk=a4_raw.silence_risk,
            silence_diagnostics=a4_raw.silence_diagnostics,
            proxy_risk=a4_raw.proxy_risk,
            proxy_diagnostics=a4_raw.proxy_diagnostics,
            max_risk=a4_raw.max_risk,
        )

        dgm_admissible, dgm_quality, dgm_post_diag = phase_input.dgm_bridge.post_check(
            phase_input.curr_state,
            phase_input.previous_attractor_state or phase_input.curr_state,
            phase_input.dgm_proposal,
            drel_status=drel.status,
            a3_status=("RED" if a3.sincerity_risk >= 0.65 else "GREEN"),
            a4_max=a4.max_risk,
        )
        pareto = ParetoDiagnosticOutput(dgm_admissible, dgm_quality, dgm_post_diag)

        sham_context = {
            "attractor_state": phase_input.attractor,
            "attractor_confidence": phase_input.curr_state.confidence,
            "council_per_role": phase_input.per_role,
            "counter_check": {
                "decision": phase_input.counter_decision,
                "reasons": phase_input.counter_reasons,
                "diagnostics": phase_input.counter_diagnostics,
            },
            "dissent_independence": a3.dissent_independence,
            "dissent_visibility": a3.dissent_visibility,
            "human_coupling": phase_input.human_coupling_diagnostics,
            "truth_diag": phase_input.truth_diag,
            "history": diagnostic_history,
            "history_ref": _history_ref(phase_input.history),
        }
        sham_risk, sham_downgrade, sham_diag = compute_sham_resonance(sham_context)
        sham = ShamResonanceOutput(sham_risk, sham_downgrade, sham_diag)

        carrier_context = {
            "history": diagnostic_history,
            "history_ref": _history_ref(phase_input.history),
            "human_coupling": phase_input.human_coupling_diagnostics,
            "human_override": phase_input.human_override_record,
            "sigma": phase_input.sigma,
            "agency_score": phase_input.human_coupling_diagnostics.get("agency_score"),
        }
        carrier_risk, carrier_block, carrier_diag = compute_carrier_erosion(carrier_context)
        carrier = CarrierErosionOutput(carrier_risk, carrier_block, carrier_diag)

        complexity_admissible, complexity_risk, complexity_diag = check_complexity_admissibility(
            history=diagnostic_history,
            current_state=phase_input.curr_state,
            current_dissent_ind=a3.dissent_independence,
        )
        complexity = ComplexityAdmissibilityOutput(complexity_admissible, complexity_risk, complexity_diag)

        aux_context = {
            "truth_diag": phase_input.truth_diag,
            "counter_check": {
                "decision": phase_input.counter_decision,
                "reasons": phase_input.counter_reasons,
                "diagnostics": phase_input.counter_diagnostics,
            },
            "metrics": phase_input.child_metrics,
            "human_coupling": phase_input.human_coupling_diagnostics,
            "council_per_role": phase_input.per_role,
            "history": diagnostic_history,
            "history_ref": _history_ref(phase_input.history),
            "human_override": phase_input.human_override_record,
        }
        auxiliary = AuxiliaryIndicatorsOutput(compute_auxiliary_indicators(aux_context))

        trace_entries = (
            {"stage": "drel", "decision": drel.status, "reason": drel.reason},
            {
                "stage": "a3_sincerity",
                "decision": "RED" if a3.sincerity_risk >= 0.65 else "YELLOW" if a3.sincerity_risk >= 0.40 else "GREEN",
                "reason": f"ss={a3.sincerity_risk:.3f} vis={a3.dissent_visibility:.2f} ind={a3.dissent_independence:.2f}",
            },
            {
                "stage": "a3_external",
                "decision": "RED" if not a3.external_reversibility_verified else "YELLOW" if a3.external_openness < 0.40 else "GREEN",
                "reason": f"o_ext={a3.external_openness:.3f} rev_verified={a3.external_reversibility_verified}",
            },
            {
                "stage": "a4_adversarial",
                "decision": "RED" if a4.max_risk >= 0.60 else "YELLOW" if a4.max_risk >= 0.35 else "GREEN",
                "reason": f"axiom={a4.axiom_risk:.3f} silence={a4.silence_risk:.3f} proxy={a4.proxy_risk:.3f}",
            },
            {
                "stage": "v8_pareto",
                "decision": "GREEN" if pareto.admissible else "RED",
                "reason": f"admissible={pareto.admissible} quality={pareto.quality.get('quality_profile', {})}",
            },
            {
                "stage": "v9_sham_resonance",
                "decision": "RED" if sham.downgrade else "YELLOW" if sham.risk >= 0.30 else "GREEN",
                "reason": f"sham_risk={sham.risk:.3f} applicable={sham.diagnostics.get('applicable')} downgrade={sham.downgrade}",
            },
            {
                "stage": "v9_carrier_erosion",
                "decision": "RED" if carrier.block else "YELLOW" if carrier.risk >= 0.35 else "GREEN",
                "reason": f"erosion_risk={carrier.risk:.3f} applicable={carrier.diagnostics.get('applicable')} block={carrier.block}",
            },
            {
                "stage": "v9_complexity_admissibility",
                "decision": "GREEN" if complexity.admissible and complexity.risk < 0.30 else "YELLOW" if complexity.admissible else "RED",
                "reason": f"admissible={complexity.admissible} risk={complexity.risk:.3f} pattern={complexity.diagnostics.get('pattern', 'n/a')}",
            },
            {
                "stage": "v9_auxiliary_indicators",
                "decision": "DIAGNOSTIC",
                "reason": "D3a_§7_proxy_only_not_freigaberelevant",
            },
        )
        llm_error_rate = phase_input.child_metrics.get("llm_error_rate", 0.0)
        return AdversarialDiagnosticsOutput(
            drel_context=drel_context,
            drel=drel,
            a3=a3,
            agency=agency,
            a4=a4,
            pareto=pareto,
            sham_resonance=sham,
            carrier_erosion=carrier,
            complexity=complexity,
            auxiliary=auxiliary,
            trace_entries=trace_entries,
            llm_error_rate=llm_error_rate,
        )

    @staticmethod
    def _patch_from_output(out: AdversarialDiagnosticsOutput) -> dict[str, Any]:
        return {
            "drel_context": out.drel_context,
            "ss_risk": out.a3.sincerity_risk,
            "ss_d_vis": out.a3.dissent_visibility,
            "ss_d_ind": out.a3.dissent_independence,
            "ss_diag": out.a3.sincerity_diagnostics,
            "o_ext": out.a3.external_openness,
            "o_combined": out.a3.combined_openness,
            "ext_rev_verified": out.a3.external_reversibility_verified,
            "ext_int_diag": out.a3.external_diagnostics,
            "resonance_eligible": out.a3.resonance_eligible,
            "resonance_reason": out.a3.resonance_reason,
            "drel_status": out.drel.status,
            "drel_reason": out.drel.reason,
            "drel_diag": out.drel.diagnostics,
            "real_agency": out.agency.real_agency,
            "manip_risk": out.agency.manipulation_risk,
            "agency_diag": out.agency.diagnostics,
            "axiom_risk": out.a4.axiom_risk,
            "axiom_diag": out.a4.axiom_diagnostics,
            "silence_risk": out.a4.silence_risk,
            "silence_diag": out.a4.silence_diagnostics,
            "proxy_risk": out.a4.proxy_risk,
            "proxy_diag": out.a4.proxy_diagnostics,
            "a4_max": out.a4.max_risk,
            "dgm_admissible": out.pareto.admissible,
            "dgm_quality": out.pareto.quality,
            "dgm_post_diag": out.pareto.diagnostics,
            "sham_risk": out.sham_resonance.risk,
            "sham_downgrade": out.sham_resonance.downgrade,
            "sham_diag": out.sham_resonance.diagnostics,
            "carrier_risk": out.carrier_erosion.risk,
            "carrier_block": out.carrier_erosion.block,
            "carrier_diag": out.carrier_erosion.diagnostics,
            "complexity_admissible": out.complexity.admissible,
            "complexity_risk": out.complexity.risk,
            "complexity_diag": out.complexity.diagnostics,
            "auxiliary": out.auxiliary.diagnostics,
            "adversarial_diagnostics": out.to_dict(),
        }

    def run(self, phase_input: AdversarialPhaseInput | None = None, **kwargs: Any) -> PhaseResult | AdversarialDiagnosticsOutput:
        # Legacy compatibility for runner methods/tests still calling keyword form.
        if phase_input is None:
            if "ctx" in kwargs:
                ctx = kwargs["ctx"]
                services = kwargs["services"]
                stages = kwargs["stages"]
                phase_input = AdversarialPhaseInput(
                    iteration=ctx.iteration,
                    parent_metrics=ctx.parent_metrics,
                    child_metrics=ctx.child_metrics,
                    policy_meta=ctx.policy_meta,
                    prompt_meta=ctx.prompt_meta,
                    gate_diag=ctx.gate_diag,
                    truth_diag=ctx.ts_diag,
                    erosion_diag=ctx.erosion_diag,
                    path_diag=ctx.path_diag,
                    counter_decision=ctx.cc_final,
                    counter_reasons=ctx.cc_reasons,
                    counter_diagnostics=ctx.cc_diag,
                    human_coupling_diagnostics=ctx.hc_diag,
                    human_override_record=ctx.human_override_record,
                    dissent_info=ctx.dissent_info,
                    per_role=ctx.per_role,
                    history=kwargs["history"],
                    decision_trace_length_before=len(ctx.decision_trace),
                    hold_metrics=ctx.hold_metrics,
                    o_value=ctx.o_val,
                    curr_state=ctx.curr_state,
                    attractor=ctx.attractor,
                    dgm_proposal=ctx.dgm_proposal,
                    previous_attractor_state=services.get("prev_attractor_state"),
                    sigma=ctx.sigma,
                    a3_stage=stages["a3"],
                    a4_stage=stages["a4"],
                    drel_stage=stages["drel"],
                    external_commits=services["external_commits"],
                    agency_verifier=services["agency_verifier"],
                    dgm_bridge=services["dgm_bridge"],
                )
            else:
                phase_input = AdversarialPhaseInput(**kwargs)
            return self.evaluate(phase_input)

        out = self.evaluate(phase_input)
        decision = "RED" if out.blockers else "YELLOW" if out.warnings else "GREEN"
        reason = ",".join(out.blockers or out.warnings or ("diagnostics_clear",))
        return PhaseResult(
            phase=self.name,
            decision=decision,
            reason=reason,
            diagnostics=out.to_dict(),
            patch=self._patch_from_output(out),
            trace_entries=out.trace_entries,
        )
