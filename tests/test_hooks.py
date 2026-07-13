"""Tests for hooks: setup_retry, after_scenario_hook, retry_report."""

from __future__ import annotations

from behave_retry import RetryConfig, after_scenario_hook, retry_report, setup_retry
from behave_retry.config import parse_retry_tag


class FakeStep:
    """Mimics behave.model.Step."""

    def __init__(self, status: str = "passed", error: Exception | None = None):
        self.status = status
        self.error = error


class FakeScenario:
    """Mimics behave.model.Scenario."""

    def __init__(
        self,
        name: str,
        tags: list[str] | None = None,
        status: str = "failed",
        steps: list[FakeStep] | None = None,
    ):
        self.name = name
        self.tags = tags or []
        self.status = status
        self.steps = steps or []

    def clear_status(self) -> None:
        self.status = "untested"


class FakeContext:
    """Mimics behave context."""

    def __init__(self):
        pass


class TestSetupRetry:
    def test_basic_setup(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        assert isinstance(ctx._behave_retry_config, RetryConfig)
        assert ctx._behave_retry_config.max_retries == 3
        assert hasattr(ctx, "_behave_retry_stats")
        assert hasattr(ctx, "_behave_retry_attempts")

    def test_with_tags(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=["@flaky"])
        assert ctx._behave_retry_config.retry_tags == ["@flaky"]

    def test_with_exceptions(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[AssertionError])
        assert ctx._behave_retry_config.retry_on == [AssertionError]

    def test_idempotent(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        setup_retry(ctx, max_retries=5)
        assert ctx._behave_retry_config.max_retries == 5


class TestAfterScenarioHook:
    def test_no_config_does_nothing(self):
        ctx = FakeContext()
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)

    def test_tracks_attempt_count(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_attempts["Login"] == 1

    def test_does_not_overwrite_existing_count(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        ctx._behave_retry_attempts["Login"] = 2
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_attempts["Login"] == 2

    def test_filename_line_used_as_key(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="failed")
        scenario.filename = "features/login.feature"
        scenario.line = 10
        after_scenario_hook(ctx, scenario)
        assert "features/login.feature:10" in ctx._behave_retry_attempts

    def test_same_name_different_line_no_collision(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        s1 = FakeScenario("Outline", status="failed")
        s1.filename = "features/test.feature"
        s1.line = 5
        s2 = FakeScenario("Outline", status="failed")
        s2.filename = "features/test.feature"
        s2.line = 15
        after_scenario_hook(ctx, s1)
        after_scenario_hook(ctx, s2)
        assert ctx._behave_retry_attempts["features/test.feature:5"] == 1
        assert ctx._behave_retry_attempts["features/test.feature:15"] == 1


class TestRetryReport:
    def test_not_configured(self):
        ctx = FakeContext()
        report = retry_report(ctx)
        assert "not configured" in report

    def test_no_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        report = retry_report(ctx)
        assert "No retries" in report

    def test_with_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        ctx._behave_retry_stats.add_retry("Login", attempts=2, final_status="passed")
        report = retry_report(ctx)
        assert "Login" in report
        assert "passed" in report


class TestParseRetryTag:
    def test_valid_tag(self):
        assert parse_retry_tag(["@retry:3"]) == 3
        assert parse_retry_tag(["@smoke", "@retry:5"]) == 5

    def test_no_tag(self):
        assert parse_retry_tag(["@smoke"]) is None
        assert parse_retry_tag([]) is None

    def test_invalid_tag(self):
        assert parse_retry_tag(["@retry:abc"]) is None
        assert parse_retry_tag(["@retry:"]) is None

    def test_first_retry_tag_wins(self):
        assert parse_retry_tag(["@retry:2", "@retry:5"]) == 2
