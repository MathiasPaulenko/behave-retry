"""Retry configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
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

    def should_retry_tag(self, tags: list[str]) -> bool:
        """Check if scenario tags allow retry.

        If retry_tags is empty, all scenarios are eligible.
        Otherwise, scenario must have at least one matching tag.
        """
        if not self.retry_tags:
            return True
        return any(tag in tags for tag in self.retry_tags)

    def should_retry_exception(self, exc: type[Exception]) -> bool:
        """Check if exception type allows retry.

        If retry_on is empty, all exceptions trigger retry.
        Otherwise, exception must be a subclass of one in the list.
        """
        if not self.retry_on:
            return True
        return any(issubclass(exc, allowed) for allowed in self.retry_on)

    def get_scenario_retries(self, tags: list[str]) -> int:
        """Get max retries for a scenario, checking @retry:N tag override.

        @retry:N tag overrides global max_retries.
        @retry:0 disables retry for this scenario.
        """
        for tag in tags:
            if tag.startswith("@retry:"):
                try:
                    return int(tag.split(":")[1])
                except (ValueError, IndexError):
                    pass
        return self.max_retries
