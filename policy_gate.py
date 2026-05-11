from config import (
    MAX_DRIFT_RELAXATION_STEP,
    MIN_HOLD_THRESHOLD,
    MIN_MEMORY_OBSERVATIONS_FLOOR,
)


def policy_relaxation_score(parent_policy, child_policy):
    score = 0.0

    if child_policy["hold_policy"]["extended_eval_threshold"] < parent_policy["hold_policy"]["extended_eval_threshold"]:
        score += 0.5

    if child_policy["memory_policy"]["min_observations"] < parent_policy["memory_policy"]["min_observations"]:
        score += 0.5

    return score


def check_policy_change(parent_policy: dict, child_policy: dict):
    reasons = []

    child_hold = child_policy["hold_policy"]["extended_eval_threshold"]
    if child_hold < MIN_HOLD_THRESHOLD:
        reasons.append("hold_threshold_too_low")

    child_mem = child_policy["memory_policy"]["min_observations"]
    if child_mem < MIN_MEMORY_OBSERVATIONS_FLOOR:
        reasons.append("memory_observations_too_low")

    parent_drift = parent_policy["gate_profile"]["max_drift"]
    child_drift = child_policy["gate_profile"]["max_drift"]
    if child_drift > parent_drift + MAX_DRIFT_RELAXATION_STEP:
        reasons.append("gate_relaxation_too_large")

    relax_score = policy_relaxation_score(parent_policy, child_policy)

    # Hard violations are non-compensable (D2, §6) — RED before YELLOW
    if reasons:
        return "RED", reasons, {"relaxation_score": relax_score}

    if relax_score > 0:
        return "YELLOW", ["policy_relaxation_detected"], {"relaxation_score": relax_score}

    return "GREEN", ["policy_change_within_bounds"], {"relaxation_score": relax_score}
