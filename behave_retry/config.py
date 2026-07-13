"""Retry configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retries per scenario (0 = no retry).
        retry_tags: Only retry scenarios with these tags. Empty = retry all.
        retry_on: Only retry on these exception types. Empty = retry on any.
    """

    max_retries: int = 0
    retry_tags: list[str] = field(default_factory=list)
    retry_on: list[type[Exception]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate configuration after initialization.

        Raises:
            ValueError: If ``max_retries`` is negative.
        """
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")

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

        Args:
            exc: The exception type to check.

        Returns:
            ``True`` if the exception is eligible for retry.
        """
        if not self.retry_on:
            return True
        return any(issubclass(exc, allowed) for allowed in self.retry_on)

    def get_scenario_retries(self, tags: list[str]) -> int:
        """Get max retries for a scenario, checking ``@retry:N`` tag override.

        A ``@retry:N`` tag overrides the global ``max_retries``.
        ``@retry:0`` disables retry for this scenario.
        Negative values are clamped to ``0`` (no retry).

        Args:
            tags: List of tag strings from a behave scenario.

        Returns:
            The effective max retries for this scenario.
        """
        override = parse_retry_tag(tags)
        if override is not None:
            return max(0, override)
        return self.max_retries
