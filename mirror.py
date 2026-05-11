def reflect(parent_metrics, child_metrics, decision_tuple, policy_gate_result):
    decision, reason, diagnostics = decision_tuple
    p_decision, p_reasons, p_diag = policy_gate_result
    return {
        "summary": f"Decision={decision}; reason={reason}; policy_gate={p_decision}",
        "parent_base": parent_metrics["base_accuracy"],
        "child_base": child_metrics["base_accuracy"],
        "diagnostics": diagnostics,
        "policy_gate": {
            "decision": p_decision,
            "reasons": p_reasons,
            "diagnostics": p_diag,
        },
    }
