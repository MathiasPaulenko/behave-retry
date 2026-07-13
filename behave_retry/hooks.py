"""Retry hooks for Behave integration."""

from __future__ import annotations

import re
from typing import Any

from .config import RetryConfig
from .stats import RetryStats


def setup_retry(
    context: Any,
    max_retries: int = 0,
    retry_tags: list[str] | None = None,
    retry_on: list[type[Exception]] | None = None,
) -> None:
    """Configure retry on the behave context.

    Call this in ``before_all`` in your ``environment.py``.

    Args:
        context: Behave context object.
        max_retries: Maximum retries per scenario (0 = no retry).
        retry_tags: Only retry scenarios with these tags.
        retry_on: Only retry on these exception types.
    """
    config = RetryConfig(
        max_retries=max_retries,
        retry_tags=retry_tags or [],
        retry_on=retry_on or [],
    )

    context._behave_retry_config = config
    context._behave_retry_stats = RetryStats()
    context._behave_retry_attempts: dict[str, int] = {}


def _get_scenario_tags(scenario: Any) -> list[str]:
    """Extract tags from a behave scenario."""
    return list(getattr(scenario, "tags", []) or [])


def _get_scenario_name(scenario: Any) -> str:
    """Get scenario name from behave scenario."""
    return getattr(scenario, "name", str(scenario))


def _get_scenario_status(scenario: Any) -> str:
    """Get scenario status from behave scenario."""
    status = getattr(scenario, "status", "failed")
    if hasattr(status, "name"):
        return status.name.lower()
    return str(status).lower()


def _get_step_status(step: Any) -> str:
    """Get step status as lowercase string."""
    status = getattr(step, "status", None)
    if status is None:
        return ""
    if hasattr(status, "name"):
        return status.name.lower()
    return str(status).lower()


def _get_scenario_exceptions(scenario: Any) -> list[str]:
    """Extract exception type names from failed steps in a scenario."""
    exceptions: list[str] = []
    for step in getattr(scenario, "steps", []) or []:
        if _get_step_status(step) == "failed":
            error = getattr(step, "error", None)
            if error is not None:
                exceptions.append(type(error).__name__)
    return exceptions


def _get_last_exception_type(scenario: Any) -> type[Exception] | None:
    """Get the exception type from the last failed step in a scenario."""
    steps = getattr(scenario, "steps", []) or []
    for step in reversed(steps):
        if _get_step_status(step) == "failed":
            error = getattr(step, "error", None)
            if error is not None:
                return type(error)
    return None


def after_scenario_hook(context: Any, scenario: Any) -> None:
    """Handle retry logic in ``after_scenario``.

    Call this in your ``after_scenario`` in ``environment.py``.

    Tracks retry attempts and records stats. The actual re-execution
    is handled by behave's runner when configured via CLI flags.
    """
    config: RetryConfig | None = getattr(context, "_behave_retry_config", None)
    if config is None:
        return

    stats: RetryStats = context._behave_retry_stats
    name = _get_scenario_name(scenario)
    tags = _get_scenario_tags(scenario)
    status = _get_scenario_status(scenario)

    attempts = context._behave_retry_attempts.get(name, 0) + 1
    context._behave_retry_attempts[name] = attempts

    if status == "passed":
        if attempts > 1:
            stats.update_retry(
                scenario=name,
                attempts=attempts,
                final_status="passed",
                exceptions=[],
            )
        return

    if status != "failed":
        return

    max_for_scenario = config.get_scenario_retries(tags)
    if max_for_scenario == 0 or not config.should_retry_tag(tags):
        return

    exc_type = _get_last_exception_type(scenario)
    if config.retry_on and (exc_type is None or not config.should_retry_exception(exc_type)):
        if attempts > 1:
            stats.update_retry(
                scenario=name,
                attempts=attempts,
                final_status="failed",
                exceptions=_get_scenario_exceptions(scenario),
            )
        return

    stats.update_retry(
        scenario=name,
        attempts=attempts,
        final_status="failed",
        exceptions=_get_scenario_exceptions(scenario),
    )


def retry_report(context: Any) -> str:
    """Get a human-readable retry summary.

    Call this in ``after_all`` in your ``environment.py``.
    """
    stats: RetryStats | None = getattr(context, "_behave_retry_stats", None)
    if stats is None:
        return "Retry Summary: behave-retry not configured."
    return stats.summary()


def parse_retry_tag(tags: list[str]) -> int | None:
    """Parse @retry:N tag from scenario tags.

    Returns N if found, None otherwise.
    """
    for tag in tags:
        match = re.match(r"^@retry:(\d+)$", tag)
        if match:
            return int(match.group(1))
    return None
