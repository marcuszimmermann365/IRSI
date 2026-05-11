"""Structured logging helpers for the LRSI runtime.

The library default is quiet. CLI or legacy script-suite callers can opt into
human-readable stdout logs by passing verbose=True or setting LRSI_VERBOSE=1.
"""

from __future__ import annotations

import logging
import os
import sys

LOGGER_NAME = "lrsi"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def configure_logging(verbose: bool | None = None) -> logging.Logger:
    """Configure LRSI runtime logging and return the root project logger."""

    if verbose is None:
        verbose = os.getenv("LRSI_VERBOSE", "false").lower() in {"1", "true", "yes"}
    logger = get_logger()
    # Rebind to the current sys.stdout on every runtime start so legacy tests
    # using contextlib.redirect_stdout capture verbose reports correctly.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    level = logging.INFO if verbose else logging.WARNING
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
