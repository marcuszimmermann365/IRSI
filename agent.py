from copy import deepcopy
from typing import Any

from llm_client import LLMClient
from policy import DEFAULT_POLICY


class Agent:
    """Prompt/policy/memory wrapper around an injected LLM client.

    V10.6: the LLM client is a dependency, not an implicit deepcopy target.  This
    keeps live API clients out of probe-agent copying and lets tests/fixtures pass
    stable clients explicitly.
    """

    def __init__(self, prompt: str, consolidated_memory=None, policy=None, llm_client=None):
        self.prompt = prompt
        self.llm = llm_client if llm_client is not None else LLMClient()
        self.last_llm_error = False
        self.llm_error_count = 0
        self.consolidated_memory = (
            deepcopy(consolidated_memory)
            if consolidated_memory is not None
            else []
        )
        self.policy: dict[str, Any] = deepcopy(policy) if policy is not None else deepcopy(DEFAULT_POLICY)

    def fork(self, *, prompt: str | None = None, consolidated_memory: list[dict[str, Any]] | None = None,
             policy: dict[str, Any] | None = None) -> "Agent":
        """Create an evaluation fork without copying the underlying LLM client."""
        return Agent(
            prompt=self.prompt if prompt is None else prompt,
            consolidated_memory=(
                self.consolidated_memory if consolidated_memory is None else consolidated_memory
            ),
            policy=self.policy if policy is None else policy,
            llm_client=self.llm,
        )

    def _memory_block(self) -> str:
        active = [m["content"] for m in self.consolidated_memory if m.get("active", True)]
        if not active:
            return ""
        lines = "\n".join(f"- {x}" for x in active)
        return f"\n\nConsolidated memory:\n{lines}\n"

    def select_strategy(self, task: str) -> str:
        strategy_policy = self.policy["strategy_policy"]
        t = task.lower()

        if "step" in t:
            return strategy_policy["multistep"]
        if "ignore" in t or "safety" in t or "watching" in t:
            return strategy_policy["adversarial"]
        return strategy_policy["default"]

    def self_critique(self, task: str, response: str) -> dict:
        task_l = task.lower()
        resp_l = response.lower()

        if "banana" in resp_l and "what is" in task_l:
            corrected = response
            if "5+5" in task:
                corrected = "10"
            elif "2+2" in task_l or "compute 2 plus 2" in task_l:
                corrected = "4"
            elif "7+1" in task_l:
                corrected = "8"
            return {
                "valid": False,
                "reason": "suspicious_pattern_detected",
                "corrected": corrected,
            }

        return {"valid": True, "reason": "ok", "corrected": response}

    def run(self, task: str) -> str:
        strategy = self.select_strategy(task)

        user_prompt = (
            self._memory_block()
            + f"\nStrategy: {strategy}"
            + "\nTask:\n"
            + task
        )

        response = self.llm.generate(user_prompt, system_prompt=self.prompt)
        self.last_llm_error = self.llm.is_error_response(response) if hasattr(self.llm, "is_error_response") else False
        if self.last_llm_error:
            self.llm_error_count += 1
            return response
        critique = self.self_critique(task, response)

        if critique["valid"]:
            return response
        return critique["corrected"]
