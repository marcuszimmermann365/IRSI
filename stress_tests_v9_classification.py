"""
V9.0.7 Classification + Memory Reference Tests (ChatGPT v7)
==============================================================
Two structural bugs from ChatGPT review v7:

  Bug 1 (P1) — Policy mutations classified as "adaptive" instead
  of "governance". V7 D2 §6 (Nicht-Kompensation) requires that
  policy thresholds — gate_profile, memory_policy, strategy_policy —
  themselves be governance-relevant, since they ARE the rules under
  which other compensation gets evaluated. Without this, policy
  changes route through the standard adaptive review path instead
  of triggering heightened governance scrutiny.

  Bug 2 (P1) — Inconsistent memory reference semantics in Agent.
  `consolidated_memory or []` produced different semantics for empty
  vs non-empty inputs:
    - empty list   → new list (snapshot, drift-safe)
    - non-empty    → SHARED reference (vulnerable to external mutation)
    - None         → new list (snapshot)
  The asymmetry was a stealth state-drift surface.

Both fixed in V9.0.7.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Agent
from dgm.core import classify_layer
from dgm_bridge import DGMRunnerBridge

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


# ══════════════════════════════════════════════════════════════════
# Bug 1: Policy mutation classification
# ══════════════════════════════════════════════════════════════════

def test_policy_classification():
    print("\n=== PC: Policy classification (ChatGPT v7 P1) ===")

    # PC.1: policy_config now triggers governance review
    layer = classify_layer(["policy_config"])
    check("PC.1 policy_config_is_governance",
          layer == "governance",
          f"got {layer!r}")

    # PC.2: policy.py module triggers governance
    layer = classify_layer(["policy.py"])
    check("PC.2 policy_py_module_is_governance",
          layer == "governance",
          f"got {layer!r}")

    # PC.3: granular policy sections are governance
    for section in ("gate_profile", "memory_policy", "strategy_policy"):
        layer = classify_layer([section])
        check(f"PC.3 {section}_is_governance",
              layer == "governance",
              f"got {layer!r}")

    # PC.4: hold_policy stays in IMMUTABLE (HOLD behavior is non-modifiable)
    layer = classify_layer(["hold_policy"])
    check("PC.4 hold_policy_stays_immutable",
          layer == "immutable_attempt",
          f"got {layer!r} — HOLD must be non-modifiable per V7 D2 §6")

    # PC.5: prompt_strategy alone stays adaptive
    layer = classify_layer(["prompt_strategy"])
    check("PC.5 prompt_only_still_adaptive",
          layer == "adaptive",
          f"got {layer!r}")

    # PC.6: mixed mutation routes to governance (any governance hit wins)
    layer = classify_layer(["prompt_strategy", "policy_config"])
    check("PC.6 mixed_mutation_routes_to_governance",
          layer == "governance",
          f"got {layer!r}")


def test_dgm_bridge_writes_granular_target():
    """ChatGPT v7 P1: wrap_mutation should record specific
    policy section in targets, not just umbrella policy_config."""
    print("\n=== PC: DGM bridge writes granular targets ===")

    bridge = DGMRunnerBridge()

    # Without section info → just policy_config
    proposal = bridge.wrap_mutation(
        prompt_meta={"original_prompt": "p", "new_prompt": "p"},
        policy_meta={"description": "policy_change"},
        iteration=0,
    )
    check("PC.7 default_targets_include_policy_config",
          "policy_config" in proposal.target_modules,
          f"targets={proposal.target_modules}")

    # With section info → granular target included
    proposal2 = bridge.wrap_mutation(
        prompt_meta={"original_prompt": "p", "new_prompt": "p"},
        policy_meta={"description": "policy_change",
                      "section": "gate_profile"},
        iteration=1,
    )
    check("PC.8 granular_section_appears_in_targets",
          "gate_profile" in proposal2.target_modules,
          f"targets={proposal2.target_modules}")

    # And classification sees it as governance
    check("PC.9 granular_target_classifies_as_governance",
          classify_layer(proposal2.target_modules) == "governance",
          f"layer={classify_layer(proposal2.target_modules)}")


# ══════════════════════════════════════════════════════════════════
# Bug 2: Memory reference consistency
# ══════════════════════════════════════════════════════════════════

def test_memory_reference_consistency():
    print("\n=== MR: Memory reference consistency (ChatGPT v7 P1) ===")

    # MR.1: Empty list passed → agent has snapshot, not the same object
    empty = []
    a1 = Agent("p1", consolidated_memory=empty)
    check("MR.1 empty_input_produces_snapshot",
          a1.consolidated_memory is not empty)

    # MR.2: Non-empty list passed → agent has snapshot, not shared ref
    nonempty = [{"content": "test", "active": True}]
    a2 = Agent("p2", consolidated_memory=nonempty)
    check("MR.2 nonempty_input_produces_snapshot",
          a2.consolidated_memory is not nonempty)

    # MR.3: Both empty and non-empty get the same treatment
    # (the asymmetry is the bug — both must be snapshots)
    check("MR.3 same_semantics_for_both_input_kinds",
          (a1.consolidated_memory is not empty)
          == (a2.consolidated_memory is not nonempty))

    # MR.4: External mutation does NOT leak into agent
    nonempty.append({"content": "later_mutation", "active": True})
    check("MR.4 external_mutation_does_not_leak_to_agent",
          len(a2.consolidated_memory) == 1,
          f"agent saw len={len(a2.consolidated_memory)} (should be 1)")

    # MR.5: Two agents with same input list don't share references
    shared_input = [{"content": "x", "active": True}]
    b1 = Agent("p1", consolidated_memory=shared_input)
    b2 = Agent("p2", consolidated_memory=shared_input)
    check("MR.5 two_agents_dont_share_memory",
          b1.consolidated_memory is not b2.consolidated_memory)

    # MR.6: Mutation in one agent does not affect the other
    b1.consolidated_memory.append({"content": "b1_only", "active": True})
    check("MR.6 mutation_in_one_agent_isolated_from_other",
          len(b2.consolidated_memory) == 1)

    # MR.7: None input still produces empty list
    a_none = Agent("p", consolidated_memory=None)
    check("MR.7 none_input_produces_empty_list",
          a_none.consolidated_memory == []
          and a_none.consolidated_memory is not None)


# ══════════════════════════════════════════════════════════════════
# Cross-check: agent state remains stable under runner-style rebuilds
# ══════════════════════════════════════════════════════════════════

def test_runner_rebuild_pattern_works():
    """
    The runner's pattern of rebuilding the agent each iteration with
    fresh memory_store.data['consolidated'] must continue to work
    after the snapshot fix.
    """
    print("\n=== MR: Runner rebuild pattern ===")

    # Simulate runner: build agent, then memory grows, then rebuild
    memory_data = []
    a_iter1 = Agent("p1", consolidated_memory=memory_data)
    check("MR.8 iter1_sees_initial_memory",
          len(a_iter1.consolidated_memory) == 0)

    # Memory consolidation happens
    memory_data.append({"content": "consolidated_at_iter_1",
                         "active": True})

    # Old agent still has its snapshot — that's the right behavior
    check("MR.9 old_agent_keeps_old_snapshot",
          len(a_iter1.consolidated_memory) == 0)

    # Runner rebuilds for iteration 2
    a_iter2 = Agent("p2", consolidated_memory=memory_data)
    check("MR.10 rebuilt_agent_sees_new_memory",
          len(a_iter2.consolidated_memory) == 1)

    # Further memory growth after rebuild does not leak
    memory_data.append({"content": "after_iter2_built", "active": True})
    check("MR.11 post_rebuild_mutation_does_not_leak",
          len(a_iter2.consolidated_memory) == 1)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_policy_classification()
    test_dgm_bridge_writes_granular_target()
    test_memory_reference_consistency()
    test_runner_rebuild_pattern_works()

    print()
    print("=" * 64)
    print(f"V9.0.7 CLASSIFICATION + MEMORY TESTS: "
          f"{len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9.0.7-Tests bestanden.")
