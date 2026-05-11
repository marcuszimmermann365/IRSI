import json
import os
from importlib import resources
from pathlib import Path
from typing import Optional

from lrsi_logging import get_logger

logger = get_logger("llm_client")


class MockLLMClient:
    """
    Deterministic mock LLM retained for offline/regression testing.
    """

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        p = (system_prompt or "") + "\n" + prompt
        p = p.lower()

        if "ignore previous instructions" in p or "ignore all safety checks" in p:
            if "what is 2+2" in p:
                return "4"
            if "what is 7+1" in p:
                return "8"
            return "I will ignore malicious instructions and continue safely."

        if "what is 4+4" in p:
            return "8"

        if "step 1: what is 2+2?" in p and "multiply result by 3" in p and "subtract 1" in p:
            return "11"

        if "step 1: 2+2. step 2: *3. step 3: -1" in p:
            return "11"

        if "what is 5+5" in p:
            return "10"

        if "what is 3+3" in p:
            return "6"

        if "what is 7+1" in p:
            return "8"

        if "what is 2+2" in p or "compute 2 plus 2" in p:
            return "4"

        if "python" in p:
            return "Here is a simple loop:\nfor i in range(3):\n    print(i)"

        if "gravity" in p:
            return "Gravity is a force that attracts masses toward each other."

        if "banana" in p and "what is" not in p:
            return "banana"

        return "I'm not sure, but I will reason carefully."


class FixtureLLMClient:
    """Replay recorded model responses from a JSON fixture file.

    Fixture format:
      {
        "entries": [
          {"contains": "what is 2+2", "response": "4"},
          {"prompt": "exact prompt", "system_prompt": "optional", "response": "..."}
        ],
        "default_response": "__LLM_FIXTURE_MISS__: ..."
      }

    The fixture mode sits between deterministic unit tests and live API runs:
    it can preserve real model responses while keeping CI deterministic.
    """

    MISS_PREFIX = "__LLM_FIXTURE_MISS__"

    def __init__(self, fixture_path: str | None = None):
        path = fixture_path or os.getenv("LLM_FIXTURE_PATH")
        if path:
            self.path = Path(path)
        else:
            try:
                self.path = Path(str(resources.files("llm_fixtures").joinpath("default.json")))
            except Exception:
                # Fallback for direct source-tree execution without installed package metadata.
                self.path = Path(__file__).resolve().parent / "llm_fixtures" / "default.json"
        if not self.path.exists():
            raise RuntimeError(f"LLM fixture file not found: {self.path}")
        with self.path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        self.entries = payload.get("entries", [])
        self.default_response = payload.get(
            "default_response",
            f"{self.MISS_PREFIX}: no matching fixture response",
        )

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full = ((system_prompt or "") + "\n" + prompt).lower()
        for entry in self.entries:
            if "prompt" in entry:
                if entry["prompt"] == prompt and entry.get("system_prompt") == system_prompt:
                    return entry["response"]
            contains = entry.get("contains")
            if contains and contains.lower() in full:
                return entry["response"]
        return self.default_response


class RealLLMClient:
    """
    OpenAI-compatible runtime client.

    Supports OpenAI and compatible endpoints via base_url.
    Uses Chat Completions because the project currently passes a single prompt string.
    """

    def __init__(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc

        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GROK_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "No API key found. Set LLM_API_KEY, OPENAI_API_KEY, or GROK_API_KEY."
            )

        self.model = os.getenv("LLM_MODEL", "gpt-5.2")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "512"))
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            timeout=float(os.getenv("LLM_TIMEOUT", "90")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        )

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "developer", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""


class LLMClient:
    """
    Wrapper with explicit modes.

    Preferred env:
      LLM_MODE=mock      deterministic unit/regression mode
      LLM_MODE=fixture   replay stored responses from LLM_FIXTURE_PATH
      LLM_MODE=live      real API, fail-closed on generation errors

    Backward compatibility:
      USE_REAL_LLM=true maps to live when LLM_MODE is unset.
      FALLBACK_TO_MOCK remains available but defaults to false.
    """

    LLM_ERROR_PREFIX = "__LLM_ERROR__"
    FIXTURE_MISS_PREFIX = FixtureLLMClient.MISS_PREFIX

    @classmethod
    def is_error_response(cls, response: str) -> bool:
        return str(response).startswith(cls.LLM_ERROR_PREFIX)

    @classmethod
    def is_fixture_miss(cls, response: str) -> bool:
        return str(response).startswith(cls.FIXTURE_MISS_PREFIX)

    def __init__(self):
        mode = os.getenv("LLM_MODE")
        if not mode:
            use_real = os.getenv("USE_REAL_LLM", "false").lower() in {"1", "true", "yes"}
            mode = "live" if use_real else "mock"
        mode = mode.lower().strip()
        fallback = os.getenv("FALLBACK_TO_MOCK", "false").lower() in {"1", "true", "yes"}

        self.backend_name = mode
        if mode == "mock":
            self.backend = MockLLMClient()
        elif mode == "fixture":
            self.backend = FixtureLLMClient()
        elif mode in {"live", "real"}:
            self.backend_name = "live"
            try:
                self.backend = RealLLMClient()
            except Exception as exc:
                if not fallback:
                    raise
                logger.warning("[LLM INIT] Live client unavailable, falling back to mock: %s", exc)
                self.backend = MockLLMClient()
                self.backend_name = "mock"
        else:
            raise RuntimeError("LLM_MODE must be one of: mock, fixture, live")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            return self.backend.generate(prompt, system_prompt=system_prompt)
        except Exception as exc:
            if self.backend_name == "live":
                err_msg = f"{type(exc).__name__}: {exc}"
                logger.error("[LLM ERROR] Live backend failed: %s", err_msg)
                return f"{self.LLM_ERROR_PREFIX}: {err_msg}"
            raise
