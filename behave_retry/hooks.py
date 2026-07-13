"""Retry hooks for Behave integration.

This module patches ``behave.model.Scenario.run`` to implement automatic
retry of failed scenarios. The patch wraps the original ``run`` method
with a retry loop that re-executes the scenario up to ``max_retries``
times when it fails.

The user-facing API is:

- :func:`setup_retry` — call in ``before_all`` to configure and activate retry.
- :func:`after_scenario_hook` — call in ``after_scenario`` to track attempts.
- :func:`retry_report` — call in ``after_all`` for a summary string.
"""

from __future__ import annotations

from typing import Any

from .config import RetryConfig, parse_retry_tag
from .stats import RetryStats

__all__ = [
    "setup_retry",
    "after_scenario_hook",
    "retry_report",
    "parse_retry_tag",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_scenario_tags(scenario: Any) -> list[str]:
    """Extract tags from a behave scenario."""
    return list(getattr(scenario, "tags", []) or [])


def _get_scenario_key(scenario: Any) -> str:
    """Get a unique key for a scenario using filename:line when available.

    Falls back to the scenario name if filename or line are missing.
    This prevents collisions between scenarios with the same name
    (e.g. Scenario Outlines).
    """
    filename = getattr(scenario, "filename", None)
    if filename is None:
        feature = getattr(scenario, "feature", None)
        if feature is not None and isinstance(feature, str):
            filename = feature
    line = getattr(scenario, "line", None)
    if filename and line is not None:
        return f"{filename}:{line}"
    return getattr(scenario, "name", str(scenario))


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


def _reset_scenario_state(scenario: Any) -> None:
    """Reset scenario and step state so it can be re-run."""
    scenario.clear_status()
    for step in getattr(scenario, "steps", []) or []:
        step.status = None
        step.error = None


# ---------------------------------------------------------------------------
# Scenario.run patch
# ---------------------------------------------------------------------------

def _patch_scenario_run(context: Any) -> None:
    """Patch ``behave.model.Scenario.run`` with a retry-aware wrapper.

    The wrapper calls the original ``run`` method. If the scenario fails
    and retries remain (per config and tag overrides), it resets the
    scenario state and calls ``run`` again.

    Stats are recorded by the wrapper after the final attempt.
    """
    try:
        from behave.model import Scenario
    except ImportError:
        return

    original_run = Scenario.run
    config: RetryConfig = context._behave_retry_config
    stats: RetryStats = context._behave_retry_stats

    def patched_run(self: Any, runner: Any) -> bool:
        tags = _get_scenario_tags(self)
        key = _get_scenario_key(self)
        name = _get_scenario_name(self)
        max_for_scenario = config.get_scenario_retries(tags)

        # No retry for this scenario — run normally.
        if max_for_scenario == 0 or not config.should_retry_tag(tags):
            return original_run(self, runner)

        attempt = 0
        while True:
            attempt += 1
            failed = original_run(self, runner)

            # Track attempt count for after_scenario_hook compatibility.
            context._behave_retry_attempts[key] = attempt

            if not failed:
                if attempt > 1:
                    stats.update_retry(
                        scenario=name,
                        attempts=attempt,
                        final_status="passed",
                        exceptions=[],
                        key=key,
                    )
                return False

            # Failed — check exception filter.
            exc_type = _get_last_exception_type(self)
            if config.retry_on and (
                exc_type is None or not config.should_retry_exception(exc_type)
            ):
                if attempt > 1:
                    stats.update_retry(
                        scenario=name,
                        attempts=attempt,
                        final_status="failed",
                        exceptions=_get_scenario_exceptions(self),
                        key=key,
                    )
                return True

            # Failed — check retry budget.
            if attempt > max_for_scenario:
                stats.update_retry(
                    scenario=name,
                    attempts=attempt,
                    final_status="failed",
                    exceptions=_get_scenario_exceptions(self),
                    key=key,
                )
                return True

            # Retry: reset scenario state and loop.
            _reset_scenario_state(self)

    Scenario.run = patched_run


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_retry(
    context: Any,
    max_retries: int = 0,
    retry_tags: list[str] | None = None,
    retry_on: list[type[Exception]] | None = None,
) -> None:
    """Configure retry on the behave context.

    Call this in ``before_all`` in your ``environment.py``.

    This patches ``behave.model.Scenario.run`` so that failed scenarios
    are automatically re-run up to ``max_retries`` times.

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

    _patch_scenario_run(context)


def after_scenario_hook(context: Any, scenario: Any) -> None:
    """Track retry attempts in ``after_scenario``.

    Call this in your ``after_scenario`` in ``environment.py``.

    With the patched ``Scenario.run``, the retry loop is handled
    automatically. This hook is kept for backward compatibility and
    tracks the attempt count on the context.
    """
    config: RetryConfig | None = getattr(context, "_behave_retry_config", None)
    if config is None:
        return

    key = _get_scenario_key(scenario)
    # The patched run already sets the attempt count.
    # If the patched run is active, this is a no-op.
    # If not (e.g., behave not installed), we track manually.
    if key not in context._behave_retry_attempts:
        context._behave_retry_attempts[key] = 1


def retry_report(context: Any) -> str:
    """Get a human-readable retry summary.

    Call this in ``after_all`` in your ``environment.py``.
    """
    stats: RetryStats | None = getattr(context, "_behave_retry_stats", None)
    if stats is None:
        return "Retry Summary: behave-retry not configured."
    return stats.summary()
