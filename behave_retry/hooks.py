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

import logging
import os
import time
from typing import Any

from .config import ExceptionFilter, RetryCallback, RetryConfig, parse_retry_tag
from .stats import RetryStats

__all__ = [
    "setup_retry",
    "after_scenario_hook",
    "retry_report",
    "parse_retry_tag",
]

logger = logging.getLogger("behave_retry")


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


def _get_feature_tags(scenario: Any) -> list[str]:
    """Extract tags from the parent feature of a behave scenario.

    Args:
        scenario: Behave scenario object with a ``feature`` attribute.

    Returns:
        List of tag strings from the parent feature, or an empty list
        if the scenario has no feature or the feature has no tags.
    """
    feature = getattr(scenario, "feature", None)
    if feature is None or isinstance(feature, str):
        return []
    return list(getattr(feature, "tags", []) or [])


def _get_scenario_key(scenario: Any) -> str:
    """Get a unique key for a scenario using filename:line:name when available.

    Falls back to the scenario name if filename or line are missing.
    Including the name prevents collisions between examples of the same
    Scenario Outline (which share filename and line but have different
    names after placeholder substitution).

    Args:
        scenario: Behave scenario object.

    Returns:
        A unique key string in ``filename:line:name`` format, or the
        scenario name as fallback.
    """
    filename = getattr(scenario, "filename", None)
    if filename is None:
        feature = getattr(scenario, "feature", None)
        if feature is not None and isinstance(feature, str):
            filename = feature
    line = getattr(scenario, "line", None)
    name = getattr(scenario, "name", None)
    if filename and line is not None:
        if name:
            return f"{filename}:{line}:{name}"
        return f"{filename}:{line}"
    return name if name else str(scenario)


def _get_scenario_name(scenario: Any) -> str:
    """Get scenario name from behave scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        The scenario name string, or ``str(scenario)`` as fallback.
    """
    return getattr(scenario, "name", str(scenario))


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
    exc = _get_last_exception(scenario)
    return type(exc) if exc is not None else None


def _get_last_exception(scenario: Any) -> Exception | None:
    """Get the exception instance from the last failed step in a scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        The exception instance of the last failed step, or ``None`` if
        no failed step has an exception.
    """
    steps = getattr(scenario, "steps", []) or []
    for step in reversed(steps):
        if _step_failed(step):
            error = getattr(step, "exception", None) or getattr(step, "error", None)
            if error is not None:
                return error
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
        from behave.model import Scenario  # type: ignore[import-untyped]
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
        stats: RetryStats | None = getattr(context, "_behave_retry_stats", None)
        if stats is None:
            return original_run(self, runner)
        tags = _get_scenario_tags(self)
        feature_tags = _get_feature_tags(self)
        key = _get_scenario_key(self)
        name = _get_scenario_name(self)
        max_for_scenario = config.get_scenario_retries(tags, feature_tags)

        all_tags = tags + feature_tags
        if max_for_scenario == 0 or not config.should_retry_tag(all_tags):
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

            total_retries = getattr(context, "_behave_retry_total", 0)
            if (
                config.max_total_retries is not None
                and total_retries >= config.max_total_retries
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

            context._behave_retry_total = total_retries + 1

            exc = _get_last_exception(self)
            exc_name = type(exc).__name__ if exc is not None else "Unknown"
            logger.info(
                'Retrying "%s" (attempt %d/%d) after %s',
                name,
                attempt,
                max_for_scenario,
                exc_name,
            )

            if config.on_retry is not None:
                config.on_retry(context, self, attempt, exc)

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
    max_retries: int | None = None,
    retry_tags: list[str] | None = None,
    retry_on: list[ExceptionFilter] | None = None,
    retry_delay: float | None = None,
    backoff_factor: float | None = None,
    on_retry: RetryCallback | None = None,
    max_total_retries: int | None = None,
) -> None:
    """Configure retry on the behave context.

    Call this in ``before_all`` in your ``environment.py``.

    This patches ``behave.model.Scenario.run`` so that failed scenarios
    are automatically re-run up to ``max_retries`` times.

    Parameters with a default of ``None`` are read from environment
    variables when not provided explicitly. This lets behave-runner or
    CI systems control retry behavior without modifying ``environment.py``.

    Args:
        context: Behave context object.
        max_retries: Maximum retries per scenario (0 = no retry).
            If ``None``, reads ``BEHAVE_RETRY_MAX_RETRIES`` (default ``0``).
        retry_tags: Only retry scenarios with these tags.
        retry_on: Only retry on these exception types.
        retry_delay: Seconds to wait before each retry (0 = no delay).
            If ``None``, reads ``BEHAVE_RETRY_DELAY`` (default ``0.0``).
        backoff_factor: Multiplier applied to ``retry_delay`` after each
            retry. Must be >= 1.0.
            If ``None``, reads ``BEHAVE_RETRY_BACKOFF`` (default ``1.0``).
        on_retry: Optional callback invoked before each retry with
            ``(context, scenario, attempt, exception)``.
        max_total_retries: Global budget for total retries across all
            scenarios. ``None`` = unlimited.
            If ``None``, reads ``BEHAVE_RETRY_MAX_TOTAL`` (default ``None``).
    """
    if max_retries is None:
        max_retries = int(os.environ.get("BEHAVE_RETRY_MAX_RETRIES", "0"))
    if retry_delay is None:
        retry_delay = float(os.environ.get("BEHAVE_RETRY_DELAY", "0.0"))
    if backoff_factor is None:
        backoff_factor = float(os.environ.get("BEHAVE_RETRY_BACKOFF", "1.0"))
    if max_total_retries is None:
        val = os.environ.get("BEHAVE_RETRY_MAX_TOTAL")
        max_total_retries = int(val) if val else None

    config = RetryConfig(
        max_retries=max_retries,
        retry_tags=retry_tags or [],
        retry_on=retry_on or [],
        retry_delay=retry_delay,
        backoff_factor=backoff_factor,
        on_retry=on_retry,
        max_total_retries=max_total_retries,
    )

    context._behave_retry_config = config
    context._behave_retry_stats = RetryStats()
    context._behave_retry_attempts = {}  # type: ignore[attr-defined]
    context._behave_retry_total = 0  # type: ignore[attr-defined]

    logger.info(
        "Retry configured: max_retries=%d, retry_tags=%s, retry_on=%s, "
        "retry_delay=%.1f, backoff_factor=%.1f, max_total_retries=%s",
        config.max_retries,
        config.retry_tags,
        [r if isinstance(r, str) else r.__name__ for r in config.retry_on],
        config.retry_delay,
        config.backoff_factor,
        config.max_total_retries,
    )

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
    summary = stats.summary()
    logger.info("Retry summary:\n%s", summary)
    return summary
