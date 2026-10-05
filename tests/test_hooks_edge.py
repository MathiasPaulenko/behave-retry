"""Edge case tests for hooks: missing attrs, weird scenarios, patch idempotency."""

from __future__ import annotations

from unittest.mock import patch

from behave_retry import RetryConfig, after_scenario_hook, retry_report, setup_retry
from behave_retry.hooks import (
    _get_last_exception_type,
    _get_scenario_exceptions,
    _get_scenario_key,
    _get_scenario_name,
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
        assert _get_scenario_key(s) == "features/x.feature:42:X"

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
        assert "f.feature:10:X" in ctx._behave_retry_attempts

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
    def __init__(self, context=None):
        self.context = context if context is not None else FakeContext()


class TestPatchScenarioRunEdge:
    def test_patch_called_multiple_times_no_crash(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(lambda self, runner: False)
            _patch_scenario_run(ctx)
            _patch_scenario_run(ctx)
            _patch_scenario_run(ctx)
            result = mock_scenario.run(FakeScenario("X"), FakeRunner(ctx))
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
            mock_scenario.run(s, FakeRunner(ctx))

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
            mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is True
        stats = ctx._behave_retry_stats
        assert stats.scenarios_retried[0].key == "features/test.feature:15:X"

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

            mock_scenario.run(s1, FakeRunner(ctx))
            mock_scenario.run(s2, FakeRunner(ctx))

        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 2
        assert stats.scenarios_retried[0].key == "a.feature:5:SameName"
        assert stats.scenarios_retried[1].key == "b.feature:10:SameName"

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

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
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is True
        assert call_count == 1


class TestResetScenarioStateEdge:
    """Edge cases for _reset_scenario_state covering step.reset, exception, error_message."""

    def test_step_with_reset_method_called(self):
        reset_called = []

        class StepWithReset:
            status = "failed"
            exception = ValueError("boom")
            error_message = "something"
            error = ValueError("err")

            def reset(self):
                reset_called.append(True)

        s = FakeScenario("X", status="failed")
        s.steps = [StepWithReset()]
        _reset_scenario_state(s)

        assert reset_called == [True]
        assert s.steps[0].exception is None
        assert s.steps[0].error_message is None
        assert s.steps[0].error is None

    def test_step_with_exception_attr_cleared(self):
        class StepWithException:
            status = "failed"
            exception = ValueError("boom")

        s = FakeScenario("X", status="failed")
        s.steps = [StepWithException()]
        _reset_scenario_state(s)

        assert s.steps[0].exception is None

    def test_step_with_error_message_attr_cleared(self):
        class StepWithErrorMessage:
            status = "failed"
            error_message = "failed badly"

        s = FakeScenario("X", status="failed")
        s.steps = [StepWithErrorMessage()]
        _reset_scenario_state(s)

        assert s.steps[0].error_message is None

    def test_step_without_exception_attr_no_error(self):
        class MinimalStep:
            status = "failed"

        s = FakeScenario("X", status="failed")
        s.steps = [MinimalStep()]
        _reset_scenario_state(s)

        assert s.steps[0].status is None

    def test_step_without_any_attrs_no_error(self):
        class BareStep:
            pass

        s = FakeScenario("X", status="failed")
        s.steps = [BareStep()]
        _reset_scenario_state(s)

    def test_scenario_without_clear_status_sets_none(self):
        class ScenarioNoClear:
            name = "X"
            tags: list[str] = []
            steps: list = []
            status = "failed"

        s = ScenarioNoClear()
        _reset_scenario_state(s)
        assert s.status is None


class TestPatchScenarioRunImportError:
    """Test _patch_scenario_run when behave.model is not available."""

    def test_import_error_returns_silently(self):
        ctx = FakeContext()
        with patch.dict("sys.modules", {"behave.model": None}):
            _patch_scenario_run(ctx)


class TestRetryOnFilterWithRetries:
    """Test that retry_on filter records stats when attempt > 1."""

    def test_retry_on_filter_after_retry_records_stats(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[ValueError])

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            if call_count == 1:
                self.steps = [FakeStep(status="failed", error=ValueError("boom"))]
            else:
                self.steps = [FakeStep(status="failed", error=TypeError("boom"))]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            s.steps = [FakeStep(status="failed", error=ValueError("boom"))]
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is True
        assert call_count == 2
        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 2
        assert stats.scenarios_retried[0].final_status == "failed"


class TestGetAllSteps:
    """_get_all_steps should prefer all_steps (includes Background steps)."""

    def test_uses_all_steps_when_present(self):
        from behave_retry.hooks import _get_all_steps

        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        bg = FakeStep(status="failed", error=ValueError("bg"))
        s.all_steps = [bg, *s.steps]
        steps = _get_all_steps(s)
        assert steps == [bg, *s.steps]

    def test_falls_back_to_steps(self):
        from behave_retry.hooks import _get_all_steps

        s = FakeScenario("X", steps=[FakeStep()])
        assert _get_all_steps(s) == s.steps

    def test_steps_none_returns_empty(self):
        from behave_retry.hooks import _get_all_steps

        s = FakeScenario("X")
        s.steps = None
        assert _get_all_steps(s) == []

    def test_all_steps_iterator_consumed(self):
        from behave_retry.hooks import _get_all_steps

        s = FakeScenario("X")
        s.all_steps = iter([FakeStep(status="failed")])
        assert len(_get_all_steps(s)) == 1


class TestBackgroundSteps:
    """Failures in Background steps must be visible to exception filtering."""

    def test_last_exception_from_background_step(self):
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        bg = FakeStep(status="failed", error=ValueError("bg"))
        s.all_steps = [bg, *s.steps]
        assert _get_last_exception_type(s) is ValueError

    def test_scenario_exceptions_include_background(self):
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        bg = FakeStep(status="failed", error=AssertionError("bg"))
        s.all_steps = [bg, *s.steps]
        assert _get_scenario_exceptions(s) == ["AssertionError"]

    def test_background_step_failure_retried_when_matching(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=2, retry_on=[ValueError])

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                bg = FakeStep(status="failed", error=ValueError("bg"))
                self.all_steps = [bg]
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is False
        assert call_count == 2

    def test_reset_clears_background_steps(self):
        bg = FakeStep(status="failed", error=ValueError("bg"))
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        s.all_steps = [bg, *s.steps]
        _reset_scenario_state(s)
        assert bg.status is None
        assert bg.error is None


class TestUnrunnableSteps:
    """Scenarios with undefined/pending steps must not be retried."""

    def test_has_unrunnable_step_undefined(self):
        from behave_retry.hooks import _has_unrunnable_step

        s = FakeScenario("X", steps=[FakeStep(status="undefined")])
        assert _has_unrunnable_step(s) is True

    def test_has_unrunnable_step_pending(self):
        from behave_retry.hooks import _has_unrunnable_step

        s = FakeScenario("X", steps=[FakeStep(status="pending")])
        assert _has_unrunnable_step(s) is True

    def test_has_unrunnable_step_normal(self):
        from behave_retry.hooks import _has_unrunnable_step

        s = FakeScenario("X", steps=[FakeStep(status="failed")])
        assert _has_unrunnable_step(s) is False

    def test_undefined_step_not_retried(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            self.steps = [FakeStep(status="undefined")]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is True
        assert call_count == 1

    def test_pending_step_not_retried(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            self.steps = [FakeStep(status="pending")]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is True
        assert call_count == 1


class TestRunnerContextResolution:
    """patched_run should use the runner's live context, not the captured one."""

    def test_runner_context_wins_over_captured(self):
        ctx1 = FakeContext()
        ctx2 = FakeContext()

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx1, max_retries=3)
            setup_retry(ctx2, max_retries=0)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner(ctx2))

        # ctx2 has max_retries=0 → no retry despite closure capturing ctx1.
        assert result is True
        assert call_count == 1

    def test_second_run_stats_go_to_own_context(self):
        ctx1 = FakeContext()
        ctx2 = FakeContext()

        def fake_run(self, runner):
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx1, max_retries=3)
            setup_retry(ctx2, max_retries=3)

            mock_scenario.run(FakeScenario("X"), FakeRunner(ctx2))

        assert "No retries" in retry_report(ctx2)

    def test_runner_without_context_falls_back_to_captured(self):
        ctx = FakeContext()

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        class BareRunner:
            context = None

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=2)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, BareRunner())

        assert result is False
        assert call_count == 2


class TestOnRetryCallbackErrors:
    """An on_retry callback that raises must not abort the test run."""

    def test_callback_exception_is_logged_and_retry_continues(self, caplog):
        import logging

        ctx = FakeContext()

        def bad_callback(context, scenario, attempt, exception):
            raise RuntimeError("callback boom")

        setup_retry(ctx, max_retries=2, on_retry=bad_callback)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with (
            caplog.at_level(logging.ERROR, logger="behave_retry"),
            patch("behave.model.Scenario") as mock_scenario,
        ):
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("X", status="failed")
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is False
        assert call_count == 2
        assert any("on_retry" in r.message for r in caplog.records)


class TestEnvVarErrors:
    """Invalid env var values must raise a clear ValueError."""

    def test_invalid_max_retries_env(self, monkeypatch):
        import pytest

        monkeypatch.setenv("BEHAVE_RETRY_MAX_RETRIES", "abc")
        with pytest.raises(ValueError, match="BEHAVE_RETRY_MAX_RETRIES"):
            setup_retry(FakeContext())

    def test_invalid_delay_env(self, monkeypatch):
        import pytest

        monkeypatch.setenv("BEHAVE_RETRY_DELAY", "soon")
        with pytest.raises(ValueError, match="BEHAVE_RETRY_DELAY"):
            setup_retry(FakeContext())

    def test_invalid_backoff_env(self, monkeypatch):
        import pytest

        monkeypatch.setenv("BEHAVE_RETRY_BACKOFF", "x2")
        with pytest.raises(ValueError, match="BEHAVE_RETRY_BACKOFF"):
            setup_retry(FakeContext())

    def test_invalid_max_total_env(self, monkeypatch):
        import pytest

        monkeypatch.setenv("BEHAVE_RETRY_MAX_TOTAL", "many")
        with pytest.raises(ValueError, match="BEHAVE_RETRY_MAX_TOTAL"):
            setup_retry(FakeContext())

    def test_empty_env_vars_use_defaults(self, monkeypatch):
        monkeypatch.setenv("BEHAVE_RETRY_MAX_RETRIES", "")
        monkeypatch.setenv("BEHAVE_RETRY_DELAY", "")
        monkeypatch.setenv("BEHAVE_RETRY_BACKOFF", "")
        monkeypatch.setenv("BEHAVE_RETRY_MAX_TOTAL", "")
        ctx = FakeContext()
        setup_retry(ctx)
        assert ctx._behave_retry_config.max_retries == 0
        assert ctx._behave_retry_config.retry_delay == 0.0
        assert ctx._behave_retry_config.backoff_factor == 1.0
        assert ctx._behave_retry_config.max_total_retries is None


class TestEffectiveTags:
    """effective_tags (includes rule-level tags) should drive tag filtering."""

    def test_rule_level_tag_makes_scenario_eligible(self):
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

            s = FakeScenario("X", tags=[], status="failed")
            s.effective_tags = {"flaky"}  # tag from parent Rule, not on scenario
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is False
        assert call_count == 2


class TestFormatterEmission:
    """Formatters are suppressed during attempts; final state emitted once."""

    def test_scenario_emitted_once_after_retries(self):
        emitted = []

        class Fmt:
            def scenario(self, s):
                emitted.append(("scenario", s.name))

            def step(self, st):
                emitted.append(("step", st.status))

            def match(self, m):
                emitted.append(("match", m))

            def result(self, st):
                emitted.append(("result", st.status))

        ctx = FakeContext()
        setup_retry(ctx, max_retries=2)

        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            assert runner.formatters == []  # suppressed during attempts
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            self.steps = [FakeStep(status="passed")]
            return False

        runner = FakeRunner(ctx)
        runner.formatters = [Fmt()]

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            _patch_scenario_run(ctx)
            mock_scenario.run(FakeScenario("X"), runner)

        scenario_events = [e for e in emitted if e[0] == "scenario"]
        assert len(scenario_events) == 1

    def test_emit_emits_step_match_result(self):
        from behave_retry.hooks import _emit_scenario_result

        emitted = []

        class Fmt:
            def scenario(self, s):
                emitted.append("scenario")

            def step(self, st):
                emitted.append("step")

            def match(self, m):
                emitted.append("match")

            def result(self, st):
                emitted.append(f"result:{st.status}")

        step = FakeStep(status="passed")
        step.match = object()
        skipped = FakeStep(status="skipped")
        s = FakeScenario("X", steps=[step, skipped])
        runner = FakeRunner()
        runner.formatters = [Fmt()]
        _emit_scenario_result(s, runner)
        # step() events for all steps first, then match/result per
        # executed step — mirrors the order behave emits them.
        assert emitted == [
            "scenario", "step", "step", "match", "result:passed",
        ]

    def test_emit_no_formatters_noop(self):
        from behave_retry.hooks import _emit_scenario_result

        runner = FakeRunner()
        runner.formatters = []
        _emit_scenario_result(FakeScenario("X"), FakeRunner())  # no crash

    def test_emit_formatter_missing_hooks(self):
        from behave_retry.hooks import _emit_scenario_result

        class BareFmt:
            def scenario(self, s):
                pass

        s = FakeScenario("X", steps=[FakeStep(status="failed", error=ValueError("x"))])
        runner = FakeRunner()
        runner.formatters = [BareFmt()]
        _emit_scenario_result(s, runner)  # no crash without step/match/result

    def test_run_quiet_without_formatters_attr(self):
        from behave_retry.hooks import _run_quiet

        ran = []

        def fake_run(self, runner):
            ran.append(1)
            return False

        class NoFmt:
            pass

        assert _run_quiet(fake_run, FakeScenario("X"), NoFmt()) is False
        assert ran == [1]

    def test_run_quiet_restores_formatters(self):
        from behave_retry.hooks import _run_quiet

        fmt = object()
        runner = FakeRunner()
        runner.formatters = [fmt]

        def fake_run(self, r):
            assert r.formatters == []
            return True

        assert _run_quiet(fake_run, FakeScenario("X"), runner) is True
        assert runner.formatters == [fmt]

    def test_resolve_step_match_returns_match(self):
        from behave_retry.hooks import _resolve_step_match

        match = object()

        class Registry:
            def find_match(self, step):
                return match

        runner = FakeRunner()
        runner.step_registry = Registry()
        assert _resolve_step_match(runner, FakeStep()) is match

    def test_resolve_step_match_undefined_returns_nomatch(self):
        from behave.matchers import NoMatch

        from behave_retry.hooks import _resolve_step_match

        class Registry:
            def find_match(self, step):
                return None

        runner = FakeRunner()
        runner.step_registry = Registry()
        assert isinstance(_resolve_step_match(runner, FakeStep()), NoMatch)

    def test_resolve_step_match_no_registry(self):
        from behave_retry.hooks import _resolve_step_match

        assert _resolve_step_match(FakeRunner(), FakeStep()) is None

    def test_resolve_step_match_nomatch_import_fails(self):
        from behave_retry.hooks import _resolve_step_match

        class Registry:
            def find_match(self, step):
                return None

        runner = FakeRunner()
        runner.step_registry = Registry()
        with patch.dict("sys.modules", {"behave.matchers": None}):
            assert _resolve_step_match(runner, FakeStep()) is None

    def test_emit_uses_registry_for_match(self):
        from behave_retry.hooks import _emit_scenario_result

        emitted = []

        class Fmt:
            def scenario(self, s):
                pass

            def step(self, s):
                pass

            def match(self, m):
                emitted.append(m)

            def result(self, s):
                pass

        match = object()

        class Registry:
            def find_match(self, step):
                return match

        runner = FakeRunner()
        runner.formatters = [Fmt()]
        runner.step_registry = Registry()
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        _emit_scenario_result(s, runner)
        assert emitted == [match]

    def test_run_quiet_restores_on_exception(self):
        from behave_retry.hooks import _run_quiet

        fmt = object()
        runner = FakeRunner()
        runner.formatters = [fmt]

        def boom(self, r):
            raise RuntimeError("x")

        import contextlib

        with contextlib.suppress(RuntimeError):
            _run_quiet(boom, FakeScenario("X"), runner)
        assert runner.formatters == [fmt]


class TestGetStats:
    def test_returns_none_without_setup(self):
        from behave_retry import get_stats

        assert get_stats(FakeContext()) is None

    def test_returns_stats_after_setup(self):
        from behave_retry import get_stats

        ctx = FakeContext()
        setup_retry(ctx)
        assert get_stats(ctx) is ctx._behave_retry_stats
