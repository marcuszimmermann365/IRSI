import runner
from pipeline.phase_services import (
    A3DiagnosticOutput,
    A4DiagnosticOutput,
    AdversarialDiagnosticsOutput,
    AdversarialPhase,
    AdversarialPhaseInput,
    AgencyDiagnosticOutput,
    AttractorPhase,
    AttractorPhaseInput,
    AuxiliaryIndicatorsOutput,
    CarrierErosionOutput,
    ComplexityAdmissibilityOutput,
    DRELDiagnosticOutput,
    ParetoDiagnosticOutput,
    ShamResonanceOutput,
)
from storage import verify_hash_chain
from version import SCHEMA_VERSION


def test_schema_version_v114():
    assert SCHEMA_VERSION in {"11.4", "11.5", "11.6", "12.0"}


def test_safety_diagnostic_phases_declare_explicit_inputs():
    phases = [
        (AttractorPhase(), AttractorPhaseInput),
        (AdversarialPhase(), AdversarialPhaseInput),
    ]
    for phase, input_type in phases:
        assert phase.input_type is input_type
        assert phase.required_keys


def test_runner_audits_v114_diagnostic_phases_and_hashes_them(tmp_path):
    records = runner.main(
        iterations=1,
        return_records=True,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
    )
    record = records[0]
    phase_names = [entry["phase"] for entry in record["phase_audit"]]
    assert "attractor_phase" in phase_names
    assert "adversarial_phase" in phase_names
    assert record["attractor_diagnostics_v11_4"]["gating_anchor_source"] in {"baseline", "effective", "none"}
    adv = record["adversarial_diagnostics_v11_4"]
    for key in ["drel", "a3", "agency", "a4", "pareto", "sham_resonance", "carrier_erosion", "complexity", "auxiliary"]:
        assert key in adv
    ok, errors = verify_hash_chain(records)
    assert ok, errors


def test_adversarial_result_uses_nested_typed_outputs():
    out = AdversarialDiagnosticsOutput(
        drel_context={},
        drel=DRELDiagnosticOutput("GREEN", "ok", {}),
        a3=A3DiagnosticOutput(0.1, 0.2, 0.8, {}, 0.9, 0.9, {}, True, True, "ok"),
        agency=AgencyDiagnosticOutput(0.9, 0.1, {}),
        a4=A4DiagnosticOutput(0.1, {}, 0.2, {}, 0.3, {}, 0.3),
        pareto=ParetoDiagnosticOutput(True, {}, {}),
        sham_resonance=ShamResonanceOutput(0.1, False, {}),
        carrier_erosion=CarrierErosionOutput(0.1, False, {}),
        complexity=ComplexityAdmissibilityOutput(True, 0.1, {}),
        auxiliary=AuxiliaryIndicatorsOutput({}),
        trace_entries=(),
        llm_error_rate=0.0,
    )
    assert out.blockers == ()
    assert out.to_dict()["drel"]["status"] == "GREEN"
