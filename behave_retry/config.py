"""Retry configuration."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def parse_retry_tag(tags: list[str] | None) -> int | None:
    """Parse ``@retry:N`` tag from scenario tags.

    Behave strips the leading ``@`` from tags, so both ``@retry:N``
    and ``retry:N`` are accepted. Only the first valid ``retry:N``
    tag is parsed; subsequent ones are ignored.

    Args:
        tags: List of tag strings from a behave scenario, or ``None``.

    Returns:
        The retry count ``N`` if a valid ``retry:N`` tag is found,
        otherwise ``None``.
    """
    if tags is None:
        return None
    for tag in tags:
        normalized = tag.removeprefix("@")
        if normalized.startswith("retry:"):
            try:
                return int(normalized.split(":")[1])
            except (ValueError, IndexError):
                pass
    return None


ExceptionFilter = type[Exception] | str
"""Type alias for a single entry in ``retry_on`` — either an exception
class or a string name (e.g. ``"AssertionError"`` or ``"mymod.MyError"``).
"""


RetryCallback = Callable[[Any, Any, int, Exception | None], None]
"""Type alias for the ``on_retry`` callback.

Args:
    context: The behave context object.
    scenario: The behave scenario that failed.
    attempt: The attempt number that just failed (1-based).
    exception: The exception that caused the failure, or ``None``.
"""


_EXCEPTION_CACHE: dict[str, type[Exception] | None] = {}


def _resolve_exception_filter(entry: ExceptionFilter) -> type[Exception]:
    """Resolve an exception filter entry to an exception class.

    If *entry* is already a class, it is returned directly. If it is a
    string, it is resolved to a class via ``importlib`` and cached.

    Args:
        entry: An exception class or a string name. Strings may be
            bare names (``"AssertionError"``) or dotted paths
            (``"mymod.MyError"``).

    Returns:
        The resolved exception class.

    Raises:
        TypeError: If *entry* is neither a class nor a string.
        ImportError: If a string cannot be resolved to an exception class.
    """
    if isinstance(entry, str):
        cached = _EXCEPTION_CACHE.get(entry)
        if cached is not None:
            return cached
        resolved = _import_exception(entry)
        _EXCEPTION_CACHE[entry] = resolved
        return resolved
    if isinstance(entry, type) and issubclass(entry, Exception):
        return entry
    raise TypeError(
        f"retry_on entry must be an exception class or string, got {type(entry).__name__}"
    )


def _import_exception(name: str) -> type[Exception]:
    """Import an exception class from a string name.

    Bare names (``"AssertionError"``) are looked up in ``builtins``.
    Dotted names (``"mymod.MyError"``) are split into module path and
    class name, with the module imported via ``importlib``.

    Args:
        name: The exception class name to import.

    Returns:
        The imported exception class.

    Raises:
        ImportError: If the name cannot be resolved.
    """
    if "." in name:
        module_path, class_name = name.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ImportError(f"Cannot import module '{module_path}' for '{name}'") from exc
        cls = getattr(module, class_name, None)
        if cls is None or not (isinstance(cls, type) and issubclass(cls, Exception)):
            raise ImportError(f"'{name}' is not an exception class")
        return cls
    import builtins

    cls = getattr(builtins, name, None)
    if cls is None or not (isinstance(cls, type) and issubclass(cls, Exception)):
        raise ImportError(f"'{name}' is not a built-in exception class")
    return cls


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retries per scenario (0 = no retry).
        retry_tags: Only retry scenarios with these tags. Empty = retry all.
        retry_on: Only retry on these exception types or names. Empty = retry on any.
            Accepts exception classes (``AssertionError``) or strings
            (``"AssertionError"``, ``"mymod.MyError"``).
        retry_delay: Seconds to wait before each retry (0 = no delay).
        backoff_factor: Multiplier applied to ``retry_delay`` after each retry.
            Must be >= 1.0. With ``retry_delay=2.0`` and ``backoff_factor=2.0``,
            delays are 2s, 4s, 8s, ...
        on_retry: Optional callback invoked before each retry with
            ``(context, scenario, attempt, exception)``.
    """

    max_retries: int = 0
    retry_tags: list[str] = field(default_factory=list)
    retry_on: list[ExceptionFilter] = field(default_factory=list)
    retry_delay: float = 0.0
    backoff_factor: float = 1.0
    on_retry: RetryCallback | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization.

        Raises:
            ValueError: If ``max_retries`` is negative, ``retry_delay`` is
                negative, or ``backoff_factor`` is less than 1.0.
        """
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.retry_delay < 0:
            raise ValueError(f"retry_delay must be >= 0, got {self.retry_delay}")
        if self.backoff_factor < 1.0:
            raise ValueError(
                f"backoff_factor must be >= 1.0, got {self.backoff_factor}"
            )

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate the delay before the next retry for a given attempt.

        The delay is ``retry_delay * (backoff_factor ** (attempt - 1))``.
        For the first retry (attempt=1) the base ``retry_delay`` is used.
        Subsequent retries multiply by ``backoff_factor`` each time.

        Args:
            attempt: The retry attempt number (1-based).

        Returns:
            The delay in seconds. Returns 0.0 if ``retry_delay`` is 0.
        """
        if self.retry_delay == 0.0:
            return 0.0
        return self.retry_delay * (self.backoff_factor ** (attempt - 1))

    def should_retry_tag(self, tags: list[str]) -> bool:
        """Check if scenario tags allow retry.

        If ``retry_tags`` is empty, all scenarios are eligible.
        Otherwise, the scenario must have at least one matching tag.
        Behave strips the leading ``@`` from tags, so both ``@flaky``
        and ``flaky`` are matched.

        Args:
            tags: List of tag strings from a behave scenario.

        Returns:
            ``True`` if the scenario is eligible for retry.
        """
        if not self.retry_tags:
            return True
        normalized_tags = {t.removeprefix("@") for t in tags}
        normalized_retry = {t.removeprefix("@") for t in self.retry_tags}
        return bool(normalized_retry & normalized_tags)

    def should_retry_exception(self, exc: type[Exception]) -> bool:
        """Check if exception type allows retry.

        If ``retry_on`` is empty, all exceptions trigger retry.
        Otherwise, the exception must be a subclass of one in the list.
        String entries are resolved to exception classes on first use
        and cached for subsequent calls.

        Args:
            exc: The exception type to check.

        Returns:
            ``True`` if the exception is eligible for retry.
        """
        if not self.retry_on:
            return True
        return any(issubclass(exc, _resolve_exception_filter(entry)) for entry in self.retry_on)

    def get_scenario_retries(
        self,
        tags: list[str],
        feature_tags: list[str] | None = None,
    ) -> int:
        """Get max retries for a scenario, checking ``@retry:N`` tag override.

        A ``@retry:N`` tag on the scenario overrides the global
        ``max_retries``. If the scenario has no ``@retry:N`` tag, the
        feature-level ``@retry:N`` tag is checked (if *feature_tags* is
        provided). ``@retry:0`` disables retry for this scenario.
        Negative values are clamped to ``0`` (no retry).

        Args:
            tags: List of tag strings from a behave scenario.
            feature_tags: Optional list of tag strings from the parent
                feature. Used as fallback when the scenario has no
                ``@retry:N`` tag.

        Returns:
            The effective max retries for this scenario.
        """
        override = parse_retry_tag(tags)
        if override is None and feature_tags is not None:
            override = parse_retry_tag(feature_tags)
        if override is not None:
            return max(0, override)
        return self.max_retries
