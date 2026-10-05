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
    "get_stats",
    "retry_report",
    "parse_retry_tag",
]

logger = logging.getLogger("behave_retry")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a clear error message.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is unset or empty.

    Returns:
        The parsed integer value, or *default*.

    Raises:
        ValueError: If the variable is set but not a valid integer.
    """
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"{name} must be an int, got {val!r}") from None


def _env_int_optional(name: str) -> int | None:
    """Read an optional integer environment variable.

    Args:
        name: Environment variable name.

    Returns:
        The parsed integer value, or ``None`` when unset or empty.

    Raises:
        ValueError: If the variable is set but not a valid integer.
    """
    val = os.environ.get(name)
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"{name} must be an int, got {val!r}") from None


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable with a clear error message.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is unset or empty.

    Returns:
        The parsed float value, or *default*.

    Raises:
        ValueError: If the variable is set but not a valid float.
    """
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        raise ValueError(f"{name} must be a float, got {val!r}") from None


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
    Behave already assigns each Scenario Outline example the line of its
    ``Examples`` row, so ``filename:line`` is unique; the name is appended
    for readability and as a guard for scenarios without line information.

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


def _get_all_steps(scenario: Any) -> list[Any]:
    """Return all executable steps of a scenario, including Background steps.

    Behave stores per-scenario copies of Background steps in
    ``scenario._background_steps`` and exposes them through
    ``scenario.all_steps``. Falls back to ``scenario.steps`` for
    objects without ``all_steps`` (e.g. duck-typed test doubles).

    Args:
        scenario: Behave scenario object.

    Returns:
        List of step objects (own steps plus Background steps).
    """
    all_steps = getattr(scenario, "all_steps", None)
    if all_steps is not None:
        return list(all_steps)
    return list(getattr(scenario, "steps", []) or [])


def _has_unrunnable_step(scenario: Any) -> bool:
    """Check if a scenario contains a step that can never pass on retry.

    Steps with status ``"undefined"`` (no matching step definition) or
    ``"pending"`` (explicitly marked as work in progress) cannot change
    outcome by re-running, so retrying is pointless.

    Args:
        scenario: Behave scenario object.

    Returns:
        ``True`` if any step has status ``"undefined"`` or ``"pending"``.
    """
    return any(
        _get_step_status(step) in ("undefined", "pending")
        for step in _get_all_steps(scenario)
    )


def _get_scenario_exceptions(scenario: Any) -> list[str]:
    """Extract exception type names from failed steps in a scenario.

    Args:
        scenario: Behave scenario object.

    Returns:
        List of exception class names (e.g. ``["AssertionError"]``).
    """
    exceptions: list[str] = []
    for step in _get_all_steps(scenario):
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
    for step in reversed(_get_all_steps(scenario)):
        if _step_failed(step):
            error = getattr(step, "exception", None) or getattr(step, "error", None)
            if error is not None:
                return error
    return None


def _reset_scenario_state(scenario: Any) -> None:
    """Reset scenario and step state so it can be re-run.

    Args:
        scenario: Behave scenario object with ``clear_status`` and
            ``all_steps``/``steps`` attributes.
    """
    if hasattr(scenario, "clear_status"):
        scenario.clear_status()
    else:
        scenario.status = None
    for step in _get_all_steps(scenario):
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


def _run_quiet(run: Any, scenario: Any, runner: Any) -> bool:
    """Run a scenario attempt with behave formatters suppressed.

    Behave re-emits ``scenario``/``step``/``match``/``result`` events to
    its formatters on every ``Scenario.run`` call, so retried scenarios
    would appear once per attempt in reports. All attempts run quietly
    and the final state is emitted once via ``_emit_scenario_result``.

    Args:
        run: The original ``Scenario.run`` method.
        scenario: The scenario being run.
        runner: The behave runner instance.

    Returns:
        ``False`` if the scenario passed, ``True`` if it failed.
    """
    formatters = getattr(runner, "formatters", None)
    if formatters is None:
        return run(scenario, runner)
    runner.formatters = []
    try:
        return run(scenario, runner)
    finally:
        runner.formatters = formatters


# Step statuses that count as "executed" — they receive match()/result()
# events when the final scenario state is emitted to formatters.
_EXECUTED_STEP_STATUSES = ("passed", "failed", "error", "undefined", "pending")


def _resolve_step_match(runner: Any, step: Any) -> Any:
    """Re-resolve the match for an executed step.

    Behave keeps the ``Match`` object as a local in ``step.run`` — it is
    not stored on the step. To emit ``formatter.match()`` after the run
    finishes, the step definition lookup is repeated. Returns a
    ``NoMatch`` for undefined steps, or ``None`` when no registry is
    available (e.g. test doubles).

    Args:
        runner: The behave runner instance.
        step: The step to resolve a match for.

    Returns:
        A ``Match``/``NoMatch`` object, or ``None``.
    """
    step_registry = getattr(runner, "step_registry", None)
    if step_registry is None:
        return None
    match = step_registry.find_match(step)
    if match is not None:
        return match
    try:
        from behave.matchers import NoMatch  # type: ignore[import-untyped]
    except ImportError:
        return None
    return NoMatch()


def _emit_scenario_result(scenario: Any, runner: Any) -> None:
    """Emit the final scenario state to behave formatters exactly once.

    Retried scenarios run with formatters suppressed so each scenario
    appears a single time in generated reports, reflecting the outcome
    of the last attempt — mirroring what an unretried ``Scenario.run``
    emits: ``scenario()``, then ``step()``/``match()``/``result()`` per
    executed step.

    Args:
        scenario: The scenario whose final state is emitted.
        runner: The behave runner instance.
    """
    formatters = getattr(runner, "formatters", None) or []
    if not formatters:
        return
    steps = _get_all_steps(scenario)
    for formatter in formatters:
        scenario_event = getattr(formatter, "scenario", None)
        if scenario_event is not None:
            scenario_event(scenario)
        step_event = getattr(formatter, "step", None)
        match_event = getattr(formatter, "match", None)
        result_event = getattr(formatter, "result", None)
        # Behave emits all step() events before running any step, then
        # match()/result() per executed step — the same order is required
        # here (e.g. pretty computes step indentations on the first match
        # assuming every step() already arrived).
        for step in steps:
            if step_event is not None:
                step_event(step)
        for step in steps:
            if _get_step_status(step) not in _EXECUTED_STEP_STATUSES:
                continue
            match = getattr(step, "match", None)
            if match is None:
                match = _resolve_step_match(runner, step)
            if match is not None and match_event is not None:
                match_event(match)
            if result_event is not None:
                result_event(step)


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
        logger.warning("behave is not installed; retry is disabled")
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
        # Prefer the runner's live context over the one captured at patch
        # time, so a second behave run in the same process uses its own
        # config and stats instead of stale state from the first run.
        ctx = getattr(runner, "context", None)
        if ctx is None:
            ctx = context
        config: RetryConfig | None = getattr(ctx, "_behave_retry_config", None)
        if config is None:
            return original_run(self, runner)
        stats: RetryStats | None = getattr(ctx, "_behave_retry_stats", None)
        if stats is None:
            return original_run(self, runner)
        tags = _get_scenario_tags(self)
        feature_tags = _get_feature_tags(self)
        key = _get_scenario_key(self)
        name = _get_scenario_name(self)
        max_for_scenario = config.get_scenario_retries(tags, feature_tags)

        # effective_tags includes feature- and rule-level tags in behave 1.3+.
        effective_tags = getattr(self, "effective_tags", None)
        all_tags = list(effective_tags) if effective_tags else tags + feature_tags
        if max_for_scenario == 0 or not config.should_retry_tag(all_tags):
            return original_run(self, runner)

        final_failed = True
        attempt = 0
        while True:
            attempt += 1
            # Formatters are suppressed on every attempt; the final
            # scenario state is emitted once after the loop so reports
            # contain a single entry per scenario.
            failed = _run_quiet(original_run, self, runner)
            attempts = getattr(ctx, "_behave_retry_attempts", None)
            if attempts is not None:
                attempts[key] = attempt

            if not failed:
                if attempt > 1:
                    stats.update_retry(
                        scenario=name,
                        attempts=attempt,
                        final_status="passed",
                        exceptions=[],
                        key=key,
                    )
                final_failed = False
                break

            # Undefined or pending steps can never pass on retry.
            if _has_unrunnable_step(self):
                break

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
                break

            if attempt > max_for_scenario:
                stats.update_retry(
                    scenario=name,
                    attempts=attempt,
                    final_status="failed",
                    exceptions=_get_scenario_exceptions(self),
                    key=key,
                )
                break

            total_retries = getattr(ctx, "_behave_retry_total", 0)
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
                break

            ctx._behave_retry_total = total_retries + 1

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
                try:
                    config.on_retry(ctx, self, attempt, exc)
                except Exception:
                    logger.exception(
                        'on_retry callback raised for "%s" (attempt %d)',
                        name,
                        attempt,
                    )

            delay = config.get_retry_delay(attempt)
            if delay > 0:
                time.sleep(delay)

            _reset_scenario_state(self)

        _emit_scenario_result(self, runner)
        return final_failed

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
        max_retries = _env_int("BEHAVE_RETRY_MAX_RETRIES", 0)
    if retry_delay is None:
        retry_delay = _env_float("BEHAVE_RETRY_DELAY", 0.0)
    if backoff_factor is None:
        backoff_factor = _env_float("BEHAVE_RETRY_BACKOFF", 1.0)
    if max_total_retries is None:
        max_total_retries = _env_int_optional("BEHAVE_RETRY_MAX_TOTAL")

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


def get_stats(context: Any) -> RetryStats | None:
    """Get the retry statistics collected during the run.

    Use this for programmatic access to retry data (e.g. JSON reports
    via ``stats.to_dict()``) instead of reading the private
    ``context._behave_retry_stats`` attribute.

    Args:
        context: Behave context object.

    Returns:
        The ``RetryStats`` instance, or ``None`` if ``setup_retry``
        was not called.
    """
    return getattr(context, "_behave_retry_stats", None)


def retry_report(context: Any) -> str:
    """Get a human-readable retry summary.

    Call this in ``after_all`` in your ``environment.py``.

    Args:
        context: Behave context object.

    Returns:
        A formatted summary string of retry statistics.
    """
    stats = get_stats(context)
    if stats is None:
        return "Retry Summary: behave-retry not configured."
    summary = stats.summary()
    logger.info("Retry summary:\n%s", summary)
    return summary
