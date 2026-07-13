"""Tests for hooks: setup_retry, after_scenario_hook, retry_report."""

from __future__ import annotations

from behave_retry import RetryConfig, after_scenario_hook, retry_report, setup_retry
from behave_retry.config import parse_retry_tag
from behave_retry.hooks import (
    _get_feature_tags,
    _get_scenario_exceptions,
    _get_scenario_key,
    _get_scenario_name,
    _get_scenario_status,
    _get_scenario_tags,
    _get_step_status,
    _patch_scenario_run,
    _reset_scenario_state,
)


class FakeStep:
    """Mimics behave.model.Step."""

    def __init__(self, status: str = "passed", error: Exception | None = None):
        self.status = status
        self.error = error


class FakeFeature:
    """Mimics behave.model.Feature."""

    def __init__(self, tags: list[str] | None = None):
        self.tags = tags or []


class FakeScenario:
    """Mimics behave.model.Scenario."""

    def __init__(
        self,
        name: str,
        tags: list[str] | None = None,
        status: str = "failed",
        steps: list[FakeStep] | None = None,
        feature: FakeFeature | None = None,
    ):
        self.name = name
        self.tags = tags or []
        self.status = status
        self.steps = steps or []
        self.feature = feature

    def clear_status(self) -> None:
        self.status = "untested"


class FakeContext:
    """Mimics behave context."""

    def __init__(self):
        pass


class FakeRunner:
    """Mimics behave runner for patch tests."""

    def __init__(self):
        self.context = FakeContext()


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

    def test_with_delay_and_backoff(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_delay=2.0, backoff_factor=2.0)
        assert ctx._behave_retry_config.retry_delay == 2.0
        assert ctx._behave_retry_config.backoff_factor == 2.0

    def test_delay_defaults(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        assert ctx._behave_retry_config.retry_delay == 0.0
        assert ctx._behave_retry_config.backoff_factor == 1.0

    def test_idempotent(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)
        setup_retry(ctx, max_retries=5)
        assert ctx._behave_retry_config.max_retries == 5

    def test_repatch_updates_delay(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_delay=1.0)
        setup_retry(ctx, max_retries=5, retry_delay=5.0, backoff_factor=3.0)
        assert ctx._behave_retry_config.retry_delay == 5.0
        assert ctx._behave_retry_config.backoff_factor == 3.0


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


class TestHelpers:
    def test_get_scenario_tags(self):
        s = FakeScenario("X", tags=["@a", "@b"])
        assert _get_scenario_tags(s) == ["@a", "@b"]

    def test_get_scenario_tags_none(self):
        s = FakeScenario("X")
        assert _get_scenario_tags(s) == []

    def test_get_scenario_key_filename_line(self):
        s = FakeScenario("X")
        s.filename = "f.feature"
        s.line = 5
        assert _get_scenario_key(s) == "f.feature:5"

    def test_get_scenario_key_name_fallback(self):
        s = FakeScenario("MyScenario")
        assert _get_scenario_key(s) == "MyScenario"

    def test_get_scenario_key_feature_string_fallback(self):
        s = FakeScenario("X")
        s.feature = "features/x.feature"
        s.line = 3
        assert _get_scenario_key(s) == "features/x.feature:3"

    def test_get_scenario_key_feature_object_ignored(self):
        s = FakeScenario("X")
        s.feature = object()
        s.line = 3
        assert _get_scenario_key(s) == "X"

    def test_get_scenario_name(self):
        s = FakeScenario("Login")
        assert _get_scenario_name(s) == "Login"

    def test_get_scenario_status_string(self):
        s = FakeScenario("X", status="failed")
        assert _get_scenario_status(s) == "failed"

    def test_get_scenario_status_enum(self):
        class FakeStatus:
            name = "PASSED"

        s = FakeScenario("X")
        s.status = FakeStatus()
        assert _get_scenario_status(s) == "passed"

    def test_get_scenario_status_default(self):
        s = FakeScenario("X")
        del s.status
        assert _get_scenario_status(s) == "failed"

    def test_get_step_status_none(self):
        step = FakeStep()
        step.status = None
        assert _get_step_status(step) == ""

    def test_get_step_status_string(self):
        step = FakeStep(status="failed")
        assert _get_step_status(step) == "failed"

    def test_get_step_status_enum(self):
        class FakeStatus:
            name = "FAILED"

        step = FakeStep()
        step.status = FakeStatus()
        assert _get_step_status(step) == "failed"

    def test_get_scenario_exceptions(self):
        s = FakeScenario(
            "X",
            steps=[
                FakeStep(status="passed"),
                FakeStep(status="failed", error=AssertionError("boom")),
            ],
        )
        excs = _get_scenario_exceptions(s)
        assert excs == ["AssertionError"]

    def test_get_scenario_exceptions_empty(self):
        s = FakeScenario("X", steps=[FakeStep(status="passed")])
        assert _get_scenario_exceptions(s) == []

    def test_get_scenario_exceptions_no_error(self):
        s = FakeScenario("X", steps=[FakeStep(status="failed")])
        assert _get_scenario_exceptions(s) == []

    def test_reset_scenario_state(self):
        step = FakeStep(status="failed", error=AssertionError("boom"))
        s = FakeScenario("X", steps=[step])
        _reset_scenario_state(s)
        assert step.status is None
        assert step.error is None


class TestPatchScenarioRun:
    """Test the Scenario.run patch with mocked behave."""

    def test_patch_without_behave(self):
        """_patch_scenario_run should not crash if behave is not installed."""
        from behave_retry.stats import RetryStats

        ctx = FakeContext()
        ctx._behave_retry_config = RetryConfig(max_retries=3)
        ctx._behave_retry_stats = RetryStats()
        ctx._behave_retry_attempts = {}
        _patch_scenario_run(ctx)

    def test_retry_loop_passes_on_second_attempt(self):
        """Scenario that fails first, passes second — stats record 2 attempts, passed."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 2
        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 2
        assert stats.scenarios_retried[0].final_status == "passed"

    def test_retry_loop_exhausted(self):
        """Scenario that always fails — stats record max+1 attempts, failed."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=2)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 3
        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 3
        assert stats.scenarios_retried[0].final_status == "failed"

    def test_no_retry_when_max_is_zero(self):
        """Scenario with @retry:0 should not retry."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", tags=["@retry:0"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1

    def test_no_retry_without_matching_tag(self):
        """Scenario without matching retry_tags should not retry."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=["@flaky"])

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", tags=["@smoke"], status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1

    def test_exception_filter_blocks_retry(self):
        """Scenario fails with non-matching exception — no retry."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[ValueError])

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            self.steps = [FakeStep(status="failed", error=AssertionError("boom"))]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is True
        assert call_count == 1

    def test_exception_filter_allows_retry(self):
        """Scenario fails with matching exception — retries."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_on=[AssertionError])

        call_count = 0

        def fake_original_run(self, runner):
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
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert call_count == 2

    def test_passes_first_time_no_stats(self):
        """Scenario passes on first attempt — no stats recorded."""
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3)

        def fake_original_run(self, runner):
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="passed")
            result = mock_scenario.run(s, FakeRunner())

        assert result is False
        assert len(ctx._behave_retry_stats.scenarios_retried) == 0


class TestRetryDelay:
    """Test that time.sleep is called with correct delays between retries."""

    def test_no_delay_no_sleep_call(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=2)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch("behave_retry.hooks.time.sleep") as mock_sleep,
        ):
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        mock_sleep.assert_not_called()

    def test_fixed_delay_between_retries(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=2, retry_delay=1.0, backoff_factor=1.0)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch("behave_retry.hooks.time.sleep") as mock_sleep,
        ):
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 1.0]

    def test_backoff_delay_between_retries(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_delay=0.5, backoff_factor=2.0)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch("behave_retry.hooks.time.sleep") as mock_sleep,
        ):
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [0.5, 1.0, 2.0]

    def test_delay_only_before_retry_not_after_pass(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_delay=2.0)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch("behave_retry.hooks.time.sleep") as mock_sleep,
        ):
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        mock_sleep.assert_called_once_with(2.0)


class TestOnRetryCallback:
    """Test the on_retry callback functionality."""

    def test_callback_called_on_retry(self):
        from unittest.mock import patch

        ctx = FakeContext()
        callback_calls: list[tuple] = []

        def my_callback(context, scenario, attempt, exception):
            callback_calls.append((context, scenario, attempt, exception))

        setup_retry(ctx, max_retries=2, on_retry=my_callback)

        call_count = 0

        def fake_original_run(self, runner):
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
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert len(callback_calls) == 1
        assert callback_calls[0][0] is ctx
        assert callback_calls[0][1] is s
        assert callback_calls[0][2] == 1
        assert isinstance(callback_calls[0][3], AssertionError)

    def test_callback_called_each_retry(self):
        from unittest.mock import patch

        ctx = FakeContext()
        callback_calls: list[int] = []

        def my_callback(context, scenario, attempt, exception):
            callback_calls.append(attempt)

        setup_retry(ctx, max_retries=3, on_retry=my_callback)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert callback_calls == [1, 2, 3]

    def test_no_callback_not_called(self):
        from unittest.mock import patch

        ctx = FakeContext()
        callback_calls: list[int] = []

        def my_callback(context, scenario, attempt, exception):
            callback_calls.append(attempt)

        setup_retry(ctx, max_retries=3)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert callback_calls == []

    def test_callback_not_called_on_pass(self):
        from unittest.mock import patch

        ctx = FakeContext()
        callback_calls: list[int] = []

        def my_callback(context, scenario, attempt, exception):
            callback_calls.append(attempt)

        setup_retry(ctx, max_retries=3, on_retry=my_callback)

        def fake_original_run(self, runner):
            self.status = "passed"
            return False

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="passed")
            mock_scenario.run(s, FakeRunner())

        assert callback_calls == []

    def test_callback_receives_none_exception_when_no_error(self):
        from unittest.mock import patch

        ctx = FakeContext()
        received_exceptions: list[Exception | None] = []

        def my_callback(context, scenario, attempt, exception):
            received_exceptions.append(exception)

        setup_retry(ctx, max_retries=2, on_retry=my_callback)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            self.steps = [FakeStep(status="failed", error=None)]
            return True

        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert received_exceptions == [None, None]

    def test_callback_called_before_delay(self):
        from unittest.mock import patch

        ctx = FakeContext()
        call_order: list[str] = []

        def my_callback(context, scenario, attempt, exception):
            call_order.append("callback")

        setup_retry(ctx, max_retries=1, retry_delay=5.0, on_retry=my_callback)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch(
                "behave_retry.hooks.time.sleep",
                side_effect=lambda x: call_order.append("sleep"),
            ),
        ):
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed")
            mock_scenario.run(s, FakeRunner())

        assert call_order == ["callback", "sleep"]

    def test_setup_retry_stores_callback(self):
        ctx = FakeContext()
        def my_callback(context, scenario, attempt, exception):
            pass
        setup_retry(ctx, max_retries=3, on_retry=my_callback)
        assert ctx._behave_retry_config.on_retry is my_callback


class TestGetFeatureTags:
    """Test the _get_feature_tags helper."""

    def test_with_feature_tags(self):
        feature = FakeFeature(tags=["@retry:3", "@flaky"])
        scenario = FakeScenario("Login", feature=feature)
        assert _get_feature_tags(scenario) == ["@retry:3", "@flaky"]

    def test_no_feature(self):
        scenario = FakeScenario("Login")
        assert _get_feature_tags(scenario) == []

    def test_feature_none(self):
        scenario = FakeScenario("Login", feature=None)
        assert _get_feature_tags(scenario) == []

    def test_feature_no_tags(self):
        feature = FakeFeature(tags=[])
        scenario = FakeScenario("Login", feature=feature)
        assert _get_feature_tags(scenario) == []

    def test_feature_string_fallback(self):
        scenario = FakeScenario("Login")
        scenario.feature = "Some Feature Name"
        assert _get_feature_tags(scenario) == []


class TestFeatureTagInheritance:
    """Test that feature-level @retry:N tags are inherited by scenarios."""

    def test_feature_retry_tag_inherited(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=0)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        feature = FakeFeature(tags=["@retry:3"])
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed", feature=feature)
            mock_scenario.run(s, FakeRunner())

        assert call_count == 3

    def test_scenario_tag_overrides_feature(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=0)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        feature = FakeFeature(tags=["@retry:5"])
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", tags=["@retry:1"], status="failed", feature=feature)
            mock_scenario.run(s, FakeRunner())

        assert call_count == 2

    def test_scenario_disable_overrides_feature(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=5)

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed"
            return True

        feature = FakeFeature(tags=["@retry:3"])
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", tags=["@retry:0"], status="failed", feature=feature)
            mock_scenario.run(s, FakeRunner())

        assert call_count == 1

    def test_feature_tag_with_retry_tags_filter(self):
        from unittest.mock import patch

        ctx = FakeContext()
        setup_retry(ctx, max_retries=3, retry_tags=["@flaky"])

        call_count = 0

        def fake_original_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.status = "failed"
                return True
            self.status = "passed"
            return False

        feature = FakeFeature(tags=["@flaky", "@retry:2"])
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_original_run)
            _patch_scenario_run(ctx)

            s = FakeScenario("Login", status="failed", feature=feature)
            mock_scenario.run(s, FakeRunner())

        assert call_count == 2
