"""Retry statistics tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioRetry:
    """Record of retry attempts for a single scenario."""

    scenario: str
    attempts: int
    final_status: str  # "passed" | "failed"
    exceptions: list[str] = field(default_factory=list)

    @property
    def was_retried(self) -> bool:
        """True if the scenario was retried at least once."""
        return self.attempts > 1

    @property
    def passed_on_retry(self) -> bool:
        """True if the scenario passed after at least one retry."""
        return self.was_retried and self.final_status == "passed"


@dataclass
class RetryStats:
    """Aggregate retry statistics for a test run."""

    total_retries: int = 0
    scenarios_retried: list[ScenarioRetry] = field(default_factory=list)

    @property
    def scenarios_passed_on_retry(self) -> int:
        return sum(1 for s in self.scenarios_retried if s.passed_on_retry)

    @property
    def scenarios_failed_after_retry(self) -> int:
        return sum(
            1 for s in self.scenarios_retried if s.final_status == "failed"
        )

    def add_retry(
        self,
        scenario: str,
        attempts: int,
        final_status: str,
        exceptions: list[str] | None = None,
    ) -> None:
        """Record a scenario that was retried."""
        self.total_retries += attempts - 1
        self.scenarios_retried.append(
            ScenarioRetry(
                scenario=scenario,
                attempts=attempts,
                final_status=final_status,
                exceptions=exceptions or [],
            )
        )

    def update_retry(
        self,
        scenario: str,
        attempts: int,
        final_status: str,
        exceptions: list[str] | None = None,
    ) -> None:
        """Update an existing retry record, or create a new one.

        If the scenario already exists in ``scenarios_retried``, its
        attempts, final_status, and exceptions are updated in place
        and ``total_retries`` is adjusted accordingly. Otherwise, a
        new entry is created via ``add_retry``.
        """
        for s in self.scenarios_retried:
            if s.scenario == scenario:
                self.total_retries -= s.attempts - 1
                s.attempts = attempts
                s.final_status = final_status
                s.exceptions = exceptions or []
                self.total_retries += attempts - 1
                return
        self.add_retry(scenario, attempts, final_status, exceptions)

    def summary(self) -> str:
        """Human-readable retry summary."""
        if not self.scenarios_retried:
            return "Retry Summary: No retries needed."

        lines = [
            "Retry Summary:",
            f"  Total retries: {self.total_retries}",
            f"  Scenarios retried: {len(self.scenarios_retried)}",
            f"  Passed on retry: {self.scenarios_passed_on_retry}",
            f"  Failed after retry: {self.scenarios_failed_after_retry}",
            "",
        ]

        for s in self.scenarios_retried:
            exc_info = f" ({', '.join(s.exceptions)})" if s.exceptions else ""
            status = "passed" if s.final_status == "passed" else "failed"
            lines.append(
                f'  - "{s.scenario}" — {s.attempts} attempts, {status}{exc_info}'
            )

        return "\n".join(lines)
