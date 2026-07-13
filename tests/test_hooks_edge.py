"""Edge case tests for hooks: missing attrs, weird scenarios, patch idempotency."""

from __future__ import annotations

from unittest.mock import patch

from behave_retry import RetryConfig, after_scenario_hook, retry_report, setup_retry
from behave_retry.hooks import (
    _get_last_exception_type,
    _get_scenario_exceptions,
    _get_scenario_key,
    _get_scenario_name,
    _get_scenario_status,
    _get_scenario_tags,
    _get_step_status,
    _patch_scenario_run,
    _reset_scenario_state,
    _step_failed,
)
from behave_retry.stats import RetryStats


class FakeStep:
    def __init__(self, status: str = "passed", error: Exception | None = None):
        self.status = status
        self.error = error


class FakeScenario:
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
    def __init__(self):
        pass


class TestHelpersEdge:
    def test_get_scenario_tags_none_attr(self):
        class NoTags:
            name = "X"

        assert _get_scenario_tags(NoTags()) == []

    def test_get_scenario_tags_is_none(self):
        class NoneTags:
            name = "X"
            tags = None

        assert _get_scenario_tags(NoneTags()) == []

    def test_get_scenario_tags_returns_copy(self):
        s = FakeScenario("X", tags=["@a"])
        tags = _get_scenario_tags(s)
        tags.append("@b")
        assert s.tags == ["@a"]

    def test_get_scenario_key_no_filename_no_line(self):
        s = FakeScenario("MyName")
        assert _get_scenario_key(s) == "MyName"

    def test_get_scenario_key_filename_no_line(self):
        s = FakeScenario("X")
        s.filename = "f.feature"
        assert _get_scenario_key(s) == "X"

    def test_get_scenario_key_no_filename_with_line(self):
        s = FakeScenario("X")
        s.line = 5
        assert _get_scenario_key(s) == "X"

    def test_get_scenario_key_filename_and_line(self):
        s = FakeScenario("X")
        s.filename = "features/x.feature"
        s.line = 42
        assert _get_scenario_key(s) == "features/x.feature:42"

    def test_get_scenario_key_feature_object_not_string(self):
        s = FakeScenario("X")
        s.feature = object()
        s.line = 3
        assert _get_scenario_key(s) == "X"

    def test_get_scenario_key_feature_none(self):
        s = FakeScenario("X")
        s.feature = None
        s.line = 3
        assert _get_scenario_key(s) == "X"

    def test_get_scenario_name_missing(self):
        class NoName:
            def __str__(self) -> str:
                return "noname"

        assert _get_scenario_name(NoName()) == "noname"

    def test_get_scenario_name_empty_string(self):
        s = FakeScenario("")
        assert _get_scenario_name(s) == ""

    def test_get_scenario_status_missing(self):
        class NoStatus:
            name = "X"

        assert _get_scenario_status(NoStatus()) == "failed"

    def test_get_scenario_status_none(self):
        s = FakeScenario("X")
        s.status = None
        assert _get_scenario_status(s) == "none"

    def test_get_scenario_status_empty_string(self):
        s = FakeScenario("X")
        s.status = ""
        assert _get_scenario_status(s) == ""

    def test_get_step_status_missing(self):
        class NoStatus:
            pass

        assert _get_step_status(NoStatus()) == ""

    def test_get_step_status_none(self):
        step = FakeStep()
        step.status = None
        assert _get_step_status(step) == ""

    def test_get_step_status_integer(self):
        step = FakeStep()
        step.status = 42
        assert _get_step_status(step) == "42"

    def test_get_scenario_exceptions_no_steps(self):
        class NoSteps:
            name = "X"

        assert _get_scenario_exceptions(NoSteps()) == []

    def test_get_scenario_exceptions_steps_none(self):
        s = FakeScenario("X")
        s.steps = None
        assert _get_scenario_exceptions(s) == []

    def test_get_scenario_exceptions_multiple_failed(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="failed", error=ValueError("a")),
                FakeStep(status="passed"),
                FakeStep(status="failed", error=TypeError("b")),
            ],
        )
        excs = _get_scenario_exceptions(s)
        assert excs == ["ValueError", "TypeError"]

    def test_get_last_exception_type_none(self):
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        assert _get_last_exception_type(s) is None

    def test_get_last_exception_type_no_steps(self):
        s = FakeScenario("X")
        assert _get_last_exception_type(s) is None

    def test_get_last_exception_type_last_failed(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="failed", error=ValueError("a")),
                FakeStep(status="failed", error=TypeError("b")),
            ],
        )
        assert _get_last_exception_type(s) is TypeError

    def test_get_last_exception_type_skips_passed(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="failed", error=ValueError("a")),
                FakeStep(status="passed"),
            ],
        )
        assert _get_last_exception_type(s) is ValueError

    def test_get_last_exception_type_no_error(self):
        s = FakeScenario("X", steps=[FakeStep(status="failed")])
        assert _get_last_exception_type(s) is None

    def test_reset_scenario_state_no_steps(self):
        class NoSteps:
            status = "failed"

            def clear_status(self) -> None:
                self.status = "untested"

        obj = NoSteps()
        _reset_scenario_state(obj)
        assert obj.status == "untested"

    def test_reset_scenario_state_no_clear_status(self):
        class NoClearStatus:
            status = "failed"

        obj = NoClearStatus()
        _reset_scenario_state(obj)
        assert obj.status is None

    def test_reset_scenario_state_steps_none(self):
        s = FakeScenario("X")
        s.steps = None
        _reset_scenario_state(s)
        assert s.status == "untested"

    def test_step_failed_with_failed_status(self):
        step = FakeStep(status="failed")
        assert _step_failed(step) is True

    def test_step_failed_with_error_status(self):
        step = FakeStep(status="error")
        assert _step_failed(step) is True

    def test_step_failed_with_passed_status(self):
        step = FakeStep(status="passed")
        assert _step_failed(step) is False

    def test_step_failed_with_none_status(self):
        step = FakeStep()
        step.status = None
        assert _step_failed(step) is False

    def test_get_scenario_exceptions_includes_error_steps(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="error", error=ValueError("boom")),
                FakeStep(status="passed"),
            ],
        )
        excs = _get_scenario_exceptions(s)
        assert excs == ["ValueError"]

    def test_get_last_exception_type_with_error_step(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="passed"),
                FakeStep(status="error", error=ValueError("boom")),
            ],
        )
        assert _get_last_exception_type(s) is ValueError

    def test_get_last_exception_type_mixed_failed_and_error(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="failed", error=AssertionError("a")),
                FakeStep(status="error", error=ValueError("b")),
            ],
        )
        assert _get_last_exception_type(s) is ValueError


class TestSetupRetryEdge:
    def test_setup_with_zero_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=0)
        assert ctx._behave_retry_config.max_retries == 0

    def test_setup_with_empty_tags(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=[])
        assert ctx._behave_retry_config.retry_tags == []

    def test_setup_with_empty_exceptions(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[])
        assert ctx._behave_retry_config.retry_on == []

    def test_setup_creates_empty_attempts(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        assert ctx._behave_retry_attempts == {}

    def test_setup_creates_fresh_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        assert isinstance(ctx._behave_retry_stats, RetryStats)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_setup_replaces_previous_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        ctx._behave_retry_stats.add_retry("X", attempts=2, final_status="passed")
        setup_retry(ctx, max_retries=5)
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_setup_multiple_times_replaces_config(self):
        ctx = FakeContext()
        for i in range(10):
            setup_retry(ctx, max_retries=i)
        assert ctx._behave_retry_config.max_retries == 9

    def test_setup_with_multiple_tags(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=["@flaky", "@smoke", "@regression"])
        assert len(ctx._behave_retry_config.retry_tags) == 3

    def test_setup_with_multiple_exceptions(self):
        ctx = FakeContext()
        setup_retry(
            ctx,
            max_retries=3,
            retry_on=[ValueError, TypeError, KeyError, AssertionError],
        )
        assert len(ctx._behave_retry_config.retry_on) == 4


class TestAfterScenarioHookEdge:
    def test_no_config_no_stats_attr(self):
        ctx = FakeContext()
        scenario = FakeScenario("X")
        after_scenario_hook(ctx, scenario)

    def test_no_config_does_not_create_attempts(self):
        ctx = FakeContext()
        scenario = FakeScenario("X")
        after_scenario_hook(ctx, scenario)
        assert not hasattr(ctx, "_behave_retry_attempts")

    def test_config_without_attempts_attr_no_crash(self):
        ctx = FakeContext()
        ctx._behave_retry_config = RetryConfig(max_retries=3)
        scenario = FakeScenario("X")
        after_scenario_hook(ctx, scenario)

    def test_with_config_and_passing_scenario(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        scenario = FakeScenario("X", status="passed")
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_attempts["X"] == 1

    def test_scenario_with_filename_key(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        s = FakeScenario("X")
        s.filename = "f.feature"
        s.line = 10
        after_scenario_hook(ctx, s)
        assert "f.feature:10" in ctx._behave_retry_attempts

    def test_pre_existing_count_not_overwritten(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        ctx._behave_retry_attempts["X"] = 5
        scenario = FakeScenario("X")
        after_scenario_hook(ctx, scenario)
        assert ctx._behave_retry_attempts["X"] == 5

    def test_multiple_scenarios_tracked(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        for i in range(10):
            after_scenario_hook(ctx, FakeScenario(f"Scenario{i}"))
        for i in range(10):
            assert ctx._behave_retry_attempts[f"Scenario{i}"] == 1


class TestRetryReportEdge:
    def test_not_configured(self):
        ctx = FakeContext()
        report = retry_report(ctx)
        assert "not configured" in report

    def test_configured_no_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        report = retry_report(ctx)
        assert "No retries" in report

    def test_with_many_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        for i in range(50):
            ctx._behave_retry_stats.add_retry(f"S{i}", attempts=2, final_status="passed")
        report = retry_report(ctx)
        assert "50" in report

    def test_with_failed_retries(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        ctx._behave_retry_stats.add_retry("X", attempts=3, final_status="failed")
        report = retry_report(ctx)
        assert "failed" in report
        assert "X" in report

    def test_stats_none(self):
        ctx = FakeContext()
        ctx._behave_retry_config = RetryConfig(max_retries=3)
        ctx._behave_retry_stats = None  # type: ignore[assignment]
        report = retry_report(ctx)
        assert "not configured" in report


class FakeRunner:
    def __init__(self):
        self.context = FakeContext()


class TestPatchScenarioRunEdge:
    def test_patch_called_multiple_times_no_crash(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(lambda self, runner: False)
            _patch_scenario_run(ctx)
            _patch_scenario_run(ctx)
            _patch_scenario_run(ctx)
            result = mock_scenario.run(FakeScenario("X"), FakeRunner())
            assert result is False

    def test_patch_idempotent_no_double_wrapping(self):
        """Multiple setup_retry calls should not double-wrap Scenario.run."""
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=2)
            setup_retry(ctx, max_retries=2)
            setup_retry(ctx, max_retries=2)

            s = FakeScenario("X", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert call_count == 3  # 1 initial + 2 retries, not 27

    def test_setup_retry_updates_config_after_repatch(self):
        """Second setup_retry with different max_retries should take effect."""
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=5)
            setup_retry(ctx, max_retries=1)

            s = FakeScenario("X", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert call_count == 2  # 1 initial + 1 retry (max_retries=1)

    def test_retry_with_tag_override_higher_than_global(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", tags=["@retry:3"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 4

    def test_retry_with_tag_override_zero(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=5)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", tags=["@retry:0"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1

    def test_retry_with_tag_filter_and_override(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1, retry_tags=["@flaky"])

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", tags=["@flaky", "@retry:3"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 2

    def test_retry_with_tag_filter_no_match_and_override(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1, retry_tags=["@flaky"])

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", tags=["@smoke", "@retry:5"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1

    def test_exception_filter_with_subclass(self):
        class CustomError(ValueError):
            pass

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[ValueError])

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                self.steps = [FakeStep(status="failed", error=CustomError("boom"))]
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 2

    def test_exception_filter_none_exception_no_retry_on(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                self.steps = [FakeStep(status="failed")]
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 2

    def test_failed_first_attempt_no_retry_records_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[ValueError])

        def fake_run(self, runner):
            self.status = "failed"
            self.steps = [FakeStep(status="failed", error=AssertionError("boom"))]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0

    def test_retry_exhausted_with_exceptions_recorded(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1)

        def fake_run(self, runner):
            self.status = "failed"
            self.steps = [FakeStep(status="failed", error=AssertionError("boom"))]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].exceptions == ["AssertionError"]

    def test_scenario_with_filename_key_in_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=2)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            s.filename = "features/test.feature"
            s.line = 15
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        stats = ctx._behave_retry_stats
        assert stats.scenarios_retried[0].key == "features/test.feature:15"

    def test_multiple_scenarios_no_key_collision(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1)

        def fake_run(self, runner):
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s1 = FakeScenario("SameName", status="failed")
            s1.filename = "a.feature"
            s1.line = 5
            s2 = FakeScenario("SameName", status="failed")
            s2.filename = "b.feature"
            s2.line = 10

            mock_scenario.run(s1, FakeRunner())
            mock_scenario.run(s2, FakeRunner())

        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 2
        assert stats.scenarios_retried[0].key == "a.feature:5"
        assert stats.scenarios_retried[1].key == "b.feature:10"

    def test_passes_on_retry_records_correct_exceptions(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                self.steps = [FakeStep(status="failed", error=AssertionError("boom"))]
                return True
            self.status = "passed"
            self.steps = []
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        stats = ctx._behave_retry_stats
        assert stats.scenarios_retried[0].final_status == "passed"
        assert stats.scenarios_retried[0].exceptions == []

    def test_attempts_tracked_on_context(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert ctx._behave_retry_attempts["X"] == 3

    def test_patched_run_without_config_falls_back(self):
        """If context loses _behave_retry_config, patched_run should
        delegate to original_run without crashing."""
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=3)

            del ctx._behave_retry_config

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1  # no retry, just original_run

    def test_patched_run_without_stats_falls_back(self):
        """If context loses _behave_retry_stats, patched_run should
        delegate to original_run without crashing."""
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=3)

            del ctx._behave_retry_stats

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1
