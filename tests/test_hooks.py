"""Tests for hooks: setup_retry, after_scenario_hook, retry_report."""

from __future__ import annotations

from behave_retry import RetryConfig, after_scenario_hook, retry_report, setup_retry
from behave_retry.hooks import parse_retry_tag


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

    def test_passed_first_time_no_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="passed")
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_failed_records_retry(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 1
        assert ctx._behave_retry_attempts["Login"] == 1

    def test_retry_tag_override_zero(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", tags=["@retry:0"], status="failed")
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_multiple_attempts_single_entry(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)
        after_scenario_hook(ctx, scenario)
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_attempts["Login"] == 3
        assert len(ctx._behave_retry_stats.scenarios_retried) == 1
        assert ctx._behave_retry_stats.scenarios_retried[0].attempts == 3
        assert ctx._behave_retry_stats.total_retries == 2

    def test_passed_after_retry_updates_entry(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("Login", status="failed")
        after_scenario_hook(ctx, scenario)
        scenario_passed = FakeScenario("Login", status="passed")
        after_scenario_hook(ctx, scenario_passed)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 1
        assert ctx._behave_retry_stats.scenarios_retried[0].final_status == "passed"
        assert ctx._behave_retry_stats.scenarios_retried[0].attempts == 2

    def test_exception_filter_blocks_retry(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[ValueError])
        scenario = FakeScenario(
            "Login",
            status="failed",
            steps=[FakeStep(status="failed", error=AssertionError("fail"))],
        )
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_exception_filter_allows_retry(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[AssertionError])
        scenario = FakeScenario(
            "Login",
            status="failed",
            steps=[FakeStep(status="failed", error=AssertionError("fail"))],
        )
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 1

    def test_exceptions_captured_from_steps(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario(
            "Login",
            status="failed",
            steps=[FakeStep(status="failed", error=AssertionError("fail"))],
        )
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_stats.scenarios_retried[0].exceptions == ["AssertionError"]

    def test_no_retry_without_matching_tag(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=["@flaky"])
        scenario = FakeScenario("Login", tags=["@smoke"], status="failed")
        after_scenario_hook(ctx, scenario)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

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
        assert len(ctx._behave_retry_stats.scenarios_retried) == 2


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
