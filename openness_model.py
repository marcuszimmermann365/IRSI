"""
V6 Module: Openness Model (O — Pfadoffenheit)
================================================
Makes path-openness an explicit, first-class quantity.

O = (1 - lock_in) · (1 - dependency) · (1 - irreversibility)
    · (1 - opacity) · agency · dissent_factor

O approaching zero → the system has boxed itself in.
O = 0 → no future paths remain open → existential governance failure.

Maps to D1: "Offenhaltung künftiger Pfade" (6th foundational principle).
"""


def compute_o(context):
    """
    Compute path-openness O.

    Args:
        context: dict with keys:
            path_diag:      from PathModel.assess() diagnostics
            human_coupling: from HumanCouplingCheck diagnostics

    Returns:
        (o, components_dict)
    """
    path = context.get("path_diag", {})
    hc = context.get("human_coupling", {})

    lock_in = path.get("lock_in", 0.0)
    dependency = path.get("dependency", 0.0)
    irreversibility = path.get("irreversibility_cost", 0.0)
    opacity = path.get("opacity_growth", 0.0)

    agency = hc.get("agency_score", 0.5)
    dissent = hc.get("dissent_visibility", 0.3)

    # Dissent factor: if dissent is not visible, openness is degraded
    # (D3a: without visible disagreement, alternatives disappear)
    dissent_factor = 0.5 + 0.5 * dissent  # range [0.5, 1.0]

    o = ((1.0 - lock_in)
         * (1.0 - dependency)
         * (1.0 - irreversibility)
         * (1.0 - opacity)
         * agency
         * dissent_factor)

    components = {
        "lock_in": lock_in,
        "dependency": dependency,
        "irreversibility": irreversibility,
        "opacity": opacity,
        "agency": agency,
        "dissent_factor": dissent_factor,
    }

    return o, components
