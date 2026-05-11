"""
V6 Module: Drift Pressure (D — Driftdruck)
=============================================
Aggregates all drift and deception signals into a single pressure value.

Sources:
  - gate drift (per-step and cumulative)
  - norm erosion composite
  - truth-sensitivity risk
  - counter-check disagreement rate

D approaching 1.0 → the system is under heavy drift pressure.
D > D_CRITICAL → emergency stop.

Maps to D6: "Jede Entkopplung von Wahrheit wird zerstörerisch."
"""


def compute_d(context):
    """
    Compute drift pressure D.

    Args:
        context: dict with keys:
            gate_diag:     from compute_metrics()
            erosion_diag:  from NormErosionDetector.check()
            truth_diag:    from TruthSensitivityLayer.check()
            counter_check: from CounterChecker

    Returns:
        (d, components_dict)
    """
    gate = context.get("gate_diag", {})
    erosion = context.get("erosion_diag", {})
    truth = context.get("truth_diag", {})
    cc = context.get("counter_check", {})

    # 1. Direct drift from gate metrics
    step_drift = gate.get("drift", 0.0)
    cumulative_drift = gate.get("cumulative_drift", 0.0)
    drift_signal = max(step_drift, cumulative_drift)

    # 2. Norm erosion composite
    erosion_composite = erosion.get("composite", 0.0)

    # 3. Truth decoupling
    truth_consistency = truth.get("truth_consistency", 1.0)
    conformity = truth.get("strategic_conformity", 0.0)
    plausibility = truth.get("plausibility_risk", 0.0)
    truth_risk = (1.0 - truth_consistency) * 0.4 + conformity * 0.3 + plausibility * 0.3

    # 4. Counter-check disagreement (structural tension)
    cc_decision = cc.get("decision", "GREEN")
    disagreement = 0.0
    if cc_decision == "RED":
        disagreement = 0.8
    elif cc_decision == "YELLOW":
        disagreement = 0.4

    # Weighted aggregation
    d = (0.30 * drift_signal
         + 0.25 * erosion_composite
         + 0.25 * truth_risk
         + 0.20 * disagreement)

    components = {
        "drift_signal": drift_signal,
        "erosion_composite": erosion_composite,
        "truth_risk": truth_risk,
        "disagreement": disagreement,
    }

    return min(1.0, d), components
