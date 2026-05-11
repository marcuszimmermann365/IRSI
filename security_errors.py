"""
Unified security error hierarchy for LRSI.

Security-relevant failures should raise LRSISecurityError or one of its
subclasses instead of generic exceptions.  The base class intentionally
inherits RuntimeError for backward compatibility with existing callers/tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class LRSISecurityError(RuntimeError):
    """Base class for security-relevant LRSI runtime failures."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        context: Mapping[str, Any] | None = None,
    ):
        self.code = code
        self.context = dict(context or {})
        context_keys = ",".join(sorted(str(key) for key in self.context.keys()))
        detail = message or code
        if context_keys:
            detail = f"{detail} | security_code={code} | context_keys={context_keys}"
        else:
            detail = f"{detail} | security_code={code}"
        super().__init__(detail)
