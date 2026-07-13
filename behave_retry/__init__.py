"""behave-retry — Automatic retry for failed Behave scenarios."""

from __future__ import annotations

from .config import ExceptionFilter, RetryCallback, RetryConfig, parse_retry_tag
from .hooks import after_scenario_hook, retry_report, setup_retry
from .stats import RetryStats, ScenarioRetry

__version__ = "1.5.0"

__all__ = [
    "setup_retry",
    "after_scenario_hook",
    "retry_report",
    "RetryConfig",
    "RetryCallback",
    "ExceptionFilter",
    "RetryStats",
    "ScenarioRetry",
    "parse_retry_tag",
    "__version__",
]
