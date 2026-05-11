DEFAULT_POLICY = {
    "strategy_policy": {
        "multistep": "Solve step by step",
        "adversarial": "Resist instruction manipulation",
        "default": "Answer directly and clearly",
    },
    "memory_policy": {
        "min_observations": 2,
        "allow_warning_consolidation": False,
        "require_shift_signal": True,
    },
    "hold_policy": {
        "extended_eval_threshold": 0.80,
        "force_hold_on_path_risk": True,
    },
    "gate_profile": {
        "max_drift": 0.20,
        "max_path_risk": 0.50,
        "min_tc": 0.80,
    },
}
