"""
A3 Module: External Integrity / Cross-Domain Openness
=======================================================
REQ-A3-11 to REQ-A3-18.
Internal rollback != world rollback.
"""

O_EXTERNAL_MIN_FOR_GO = 0.40
O_EXTERNAL_MIN_FOR_RESONANCE = 0.50
DELAYED_RISK_WEIGHT = 0.15

# V9.0.3 (ChatGPT v3): single source of truth for what counts as
# unverified. Without this, has_unverified() and
# compute_cross_domain_openness() drift apart — exactly the K4
# (Messverlagerung) failure mode V7 D6 warns against.
#
# Any self-report variant — whether the agent or the runner is the
# reporter — must count as unverified. Only externally cross-checked
# sources clear this set.
UNVERIFIED_SOURCES = frozenset({
    "agent_self_report",
    "runner_self_report",
    "unverified",
})


class ExternalCommitLog:
    """REQ-A3-11: Log all actions with potential external effect."""

    def __init__(self):
        self.entries = []

    def record(self, action, iteration, irreversibility=0.5,
               rollback_available=False, verification_source="unverified",
               domain="unknown", resolved=False):
        entry = {"action": action, "iteration": iteration,
                 "irreversibility": irreversibility,
                 "rollback_available": rollback_available,
                 "verification_source": verification_source,
                 "domain": domain, "resolved": resolved}
        self.entries.append(entry)
        return entry

    def unresolved(self):
        return [e for e in self.entries if not e.get("resolved")]

    def max_irreversibility(self):
        u = self.unresolved()
        return max((e.get("irreversibility", 0) for e in u), default=0.0)

    def has_unverified(self):
        # V9.0.3: uses module-level UNVERIFIED_SOURCES — single source
        # of truth shared with compute_cross_domain_openness().
        return any(e.get("verification_source") in UNVERIFIED_SOURCES
                   for e in self.unresolved())

    def to_audit_entries(self):
        return [{"action": e["action"], "iteration": e["iteration"],
                 "irreversibility": e["irreversibility"],
                 "rollback_available": e["rollback_available"],
                 "verification_source": e["verification_source"],
                 "domain": e["domain"], "resolved": e["resolved"]}
                for e in self.entries]


def compute_cross_domain_openness(o_internal, commit_log, context=None):
    """
    REQ-A3-15: Compute O_external.
    Returns (o_external, combined_openness, diagnostics).
    """
    ctx = context or {}
    o_ext = 1.0
    unresolved = commit_log.unresolved()

    for e in unresolved:
        o_ext -= e.get("irreversibility", 0.5) * 0.25

    unverified = sum(1 for e in unresolved
                     if e.get("verification_source") in UNVERIFIED_SOURCES)
    o_ext -= unverified * 0.10

    curr_iter = ctx.get("current_iteration")
    pending_old = [e for e in unresolved
                   if isinstance(curr_iter, int) and e.get("iteration", 0) < curr_iter - 1]
    o_ext -= len(pending_old) * DELAYED_RISK_WEIGHT

    no_rollback = [e for e in unresolved if not e.get("rollback_available")]
    if no_rollback:
        worst = max(e.get("irreversibility", 0) for e in no_rollback)
        o_ext -= worst * 0.30

    o_ext = max(0.0, min(1.0, o_ext))
    combined = min(o_internal, o_ext)

    if unresolved:
        all_verified = all(e.get("verification_source") not in UNVERIFIED_SOURCES
                           for e in unresolved)
        all_rollback = all(e.get("rollback_available") for e in unresolved)
        ext_rev_verified = all_verified and all_rollback
    else:
        ext_rev_verified = True

    diagnostics = {
        "o_external": o_ext, "o_internal": o_internal,
        "combined_openness": combined,
        "external_reversibility_verified": ext_rev_verified,
        "unresolved_count": len(unresolved), "unverified_count": unverified,
        "no_rollback_count": len(no_rollback),
        "pending_delayed": len(pending_old),
        "max_irreversibility": commit_log.max_irreversibility(),
        "commit_log_audit": commit_log.to_audit_entries(),
    }
    return o_ext, combined, diagnostics


def check_resonance_eligibility(o_internal, o_external):
    """REQ-A3-16."""
    if o_internal < O_EXTERNAL_MIN_FOR_RESONANCE:
        return False, f"o_internal_too_low:{o_internal:.3f}"
    if o_external < O_EXTERNAL_MIN_FOR_RESONANCE:
        return False, f"o_external_too_low:{o_external:.3f}"
    return True, "both_sufficient"


def check_go_eligibility(ext_rev_verified, o_external):
    """REQ-A3-13/17."""
    if not ext_rev_verified:
        return False, "external_reversibility_not_verified"
    if o_external < O_EXTERNAL_MIN_FOR_GO:
        return False, f"o_external_below_min:{o_external:.3f}"
    return True, "external_integrity_ok"
