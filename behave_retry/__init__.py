"""behave-retry — Automatic retry for failed Behave scenarios."""

from __future__ import annotations

from .config import RetryConfig
from .exceptions import RetryExhaustedError
from .hooks import after_scenario_hook, retry_report, setup_retry
from .stats import RetryStats, ScenarioRetry

__version__ = "1.0.1"

__all__ = [
    "setup_retry",
    "after_scenario_hook",
    "retry_report",
    "RetryConfig",
    "RetryStats",
    "ScenarioRetry",
    "RetryExhaustedError",
    "__version__",
]
