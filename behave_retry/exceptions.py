"""Custom exceptions for behave-retry."""

from __future__ import annotations


class RetryExhaustedError(Exception):
    """Raised when a scenario has been retried the maximum number of times."""

    def __init__(self, scenario: str, attempts: int) -> None:
        super().__init__(
            f"Scenario {scenario!r} failed after {attempts} attempt(s)"
        )
        self.scenario = scenario
        self.attempts = attempts
