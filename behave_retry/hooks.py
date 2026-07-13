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

import time
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
    """Extract tags from a behave scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        List of tag strings, or an empty list if the scenario has none.
    """
    return list(getattr(scenario, "tags", []) or [])


def _get_scenario_key(scenario: Any) -> str:
    """Get a unique key for a scenario using filename:line when available.

    Falls back to the scenario name if filename or line are missing.
    This prevents collisions between scenarios with the same name
    (e.g. Scenario Outlines).

    Args:
        scenario: Behave scenario object.

    Returns:
        A unique key string in ``filename:line`` format, or the
        scenario name as fallback.
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
    """Get scenario name from behave scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        The scenario name string, or ``str(scenario)`` as fallback.
    """
    return getattr(scenario, "name", str(scenario))


def _get_scenario_status(scenario: Any) -> str:
    """Get scenario status from behave scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        Lowercase status string (e.g. ``"passed"``, ``"failed"``).
        Defaults to ``"failed"`` if the scenario has no status attribute.
    """
    status = getattr(scenario, "status", "failed")
    if hasattr(status, "name"):
        return status.name.lower()
    return str(status).lower()


def _get_step_status(step: Any) -> str:
    """Get step status as lowercase string.

    Args:
        step: Behave step object.

    Returns:
        Lowercase status string, or an empty string if the step
        has no status or it is ``None``.
    """
    status = getattr(step, "status", None)
    if status is None:
        return ""
    if hasattr(status, "name"):
        return status.name.lower()
    return str(status).lower()


def _step_failed(step: Any) -> bool:
    """Check if a step failed or errored.

    Behave assigns ``Status.failed`` to ``AssertionError`` and
    ``Status.error`` to other exceptions. Both should be treated
    as failures for retry purposes.

    Args:
        step: Behave step object.

    Returns:
        ``True`` if the step status is ``"failed"`` or ``"error"``.
    """
    status = _get_step_status(step)
    return status in ("failed", "error")


def _get_scenario_exceptions(scenario: Any) -> list[str]:
    """Extract exception type names from failed steps in a scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        List of exception class names (e.g. ``["AssertionError"]``).
    """
    exceptions: list[str] = []
    for step in getattr(scenario, "steps", []) or []:
        if _step_failed(step):
            error = getattr(step, "exception", None) or getattr(step, "error", None)
            if error is not None:
                exceptions.append(type(error).__name__)
    return exceptions


def _get_last_exception_type(scenario: Any) -> type[Exception] | None:
    """Get the exception type from the last failed step in a scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        The exception type of the last failed step, or ``None`` if
        no failed step has an exception.
    """
    steps = getattr(scenario, "steps", []) or []
    for step in reversed(steps):
        if _step_failed(step):
            error = getattr(step, "exception", None) or getattr(step, "error", None)
            if error is not None:
                return type(error)
    return None


def _reset_scenario_state(scenario: Any) -> None:
    """Reset scenario and step state so it can be re-run.

    Args:
        scenario: Behave scenario object with ``clear_status`` and
            ``steps`` attributes.
    """
    if hasattr(scenario, "clear_status"):
        scenario.clear_status()
    else:
        scenario.status = None
    for step in getattr(scenario, "steps", []) or []:
        if hasattr(step, "reset"):
            step.reset()
        else:
            step.status = None
        if hasattr(step, "exception"):
            step.exception = None
        if hasattr(step, "error_message"):
            step.error_message = None
        if hasattr(step, "error"):
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

    if getattr(original_run, "_behave_retry_patched", False):
        return

    def patched_run(self: Any, runner: Any) -> bool:
        """Retry-aware wrapper for ``Scenario.run``.

        Args:
            self: The behave scenario instance.
            runner: The behave runner instance.

        Returns:
            ``False`` if the scenario passed, ``True`` if it failed
            after exhausting all retries.
        """
        config: RetryConfig | None = getattr(context, "_behave_retry_config", None)
        if config is None:
            return original_run(self, runner)
        stats: RetryStats = getattr(context, "_behave_retry_stats", None)
        if stats is None:
            return original_run(self, runner)
        tags = _get_scenario_tags(self)
        key = _get_scenario_key(self)
        name = _get_scenario_name(self)
        max_for_scenario = config.get_scenario_retries(tags)

        if max_for_scenario == 0 or not config.should_retry_tag(tags):
            return original_run(self, runner)

        attempt = 0
        while True:
            attempt += 1
            failed = original_run(self, runner)
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

            exc_type = _get_last_exception_type(self)
            if config.retry_on and (
                exc_type is None
                or not config.should_retry_exception(exc_type)
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

            if attempt > max_for_scenario:
                stats.update_retry(
                    scenario=name,
                    attempts=attempt,
                    final_status="failed",
                    exceptions=_get_scenario_exceptions(self),
                    key=key,
                )
                return True

            delay = config.get_retry_delay(attempt)
            if delay > 0:
                time.sleep(delay)

            _reset_scenario_state(self)

    Scenario.run = patched_run
    patched_run._behave_retry_patched = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_retry(
    context: Any,
    max_retries: int = 0,
    retry_tags: list[str] | None = None,
    retry_on: list[type[Exception]] | None = None,
    retry_delay: float = 0.0,
    backoff_factor: float = 1.0,
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
        retry_delay: Seconds to wait before each retry (0 = no delay).
        backoff_factor: Multiplier applied to ``retry_delay`` after each
            retry. Must be >= 1.0.
    """
    config = RetryConfig(
        max_retries=max_retries,
        retry_tags=retry_tags or [],
        retry_on=retry_on or [],
        retry_delay=retry_delay,
        backoff_factor=backoff_factor,
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

    Args:
        context: Behave context object.
        scenario: The behave scenario that just finished.
    """
    config: RetryConfig | None = getattr(context, "_behave_retry_config", None)
    if config is None:
        return

    attempts: dict[str, int] | None = getattr(
        context, "_behave_retry_attempts", None,
    )
    if attempts is None:
        return

    key = _get_scenario_key(scenario)
    if key not in attempts:
        attempts[key] = 1


def retry_report(context: Any) -> str:
    """Get a human-readable retry summary.

    Call this in ``after_all`` in your ``environment.py``.

    Args:
        context: Behave context object.

    Returns:
        A formatted summary string of retry statistics.
    """
    stats: RetryStats | None = getattr(context, "_behave_retry_stats", None)
    if stats is None:
        return "Retry Summary: behave-retry not configured."
    return stats.summary()
