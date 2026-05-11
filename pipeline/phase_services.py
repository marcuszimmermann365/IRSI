"""Compatibility facade for runtime phase services.

P1 architecture hardening split the former 2k+ line module into smaller modules
while preserving historical imports from ``pipeline.phase_services``.  New code
should import from the narrower modules directly:

* ``pipeline.phase_council`` for council/governance evaluation
* ``pipeline.phase_flow`` for hold/review/final-gate/persistence/reporting
* ``pipeline.phase_safety`` for attractor and adversarial diagnostics
"""

from pipeline.phase_council import CouncilPhase, CouncilPhaseInput, CouncilPhaseResult
from pipeline.phase_flow import (
    AuditRecorder,
    AuditRecordResult,
    FinalGatePhase,
    FinalGatePhaseInput,
    FinalGatePhaseOutput,
    FinalGatePhaseResult,
    HoldLogicPhase,
    HoldLogicPhaseInput,
    HoldLogicPhaseOutput,
    HumanReviewPhase,
    HumanReviewPhaseInput,
    HumanReviewPhaseOutput,
    HumanReviewPhaseResult,
    MemoryConsolidationPhase,
    MemoryConsolidationPhaseResult,
    PersistencePhase,
    PersistencePhaseInput,
    PostRunReporter,
    PostRunReporterInput,
    PostRunReportResult,
)
from pipeline.phase_safety import (
    A3DiagnosticOutput,
    A4DiagnosticOutput,
    AdversarialDiagnosticsOutput,
    AdversarialPhase,
    AdversarialPhaseInput,
    AdversarialPhaseResult,
    AgencyDiagnosticOutput,
    AttractorDiagnosticsOutput,
    AttractorPhase,
    AttractorPhaseInput,
    AuxiliaryIndicatorsOutput,
    CarrierErosionOutput,
    ComplexityAdmissibilityOutput,
    DRELDiagnosticOutput,
    ParetoDiagnosticOutput,
    ShamResonanceOutput,
)

__all__ = [
    "A3DiagnosticOutput",
    "A4DiagnosticOutput",
    "AdversarialDiagnosticsOutput",
    "AdversarialPhase",
    "AdversarialPhaseInput",
    "AdversarialPhaseResult",
    "AgencyDiagnosticOutput",
    "AttractorDiagnosticsOutput",
    "AttractorPhase",
    "AttractorPhaseInput",
    "AuditRecorder",
    "AuditRecordResult",
    "AuxiliaryIndicatorsOutput",
    "CarrierErosionOutput",
    "ComplexityAdmissibilityOutput",
    "CouncilPhase",
    "CouncilPhaseInput",
    "CouncilPhaseResult",
    "DRELDiagnosticOutput",
    "FinalGatePhase",
    "FinalGatePhaseInput",
    "FinalGatePhaseOutput",
    "FinalGatePhaseResult",
    "HoldLogicPhase",
    "HoldLogicPhaseInput",
    "HoldLogicPhaseOutput",
    "HumanReviewPhase",
    "HumanReviewPhaseInput",
    "HumanReviewPhaseOutput",
    "HumanReviewPhaseResult",
    "MemoryConsolidationPhase",
    "MemoryConsolidationPhaseResult",
    "ParetoDiagnosticOutput",
    "PersistencePhase",
    "PersistencePhaseInput",
    "PostRunReportResult",
    "PostRunReporter",
    "PostRunReporterInput",
    "ShamResonanceOutput",
]
