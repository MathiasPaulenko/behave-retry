"""Regression tests for formatter emission, dry-run, and hook robustness fixes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from behave_retry import setup_retry


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


class FakeRunner:
    def __init__(self, context=None):
        self.context = context if context is not None else FakeContext()


class TestShouldEmitResult:
    def test_no_should_run_attr_defaults_true(self):
        from behave_retry.hooks import _should_emit_result

        assert _should_emit_result(FakeScenario("X"), FakeRunner()) is True

    def test_should_run_false_suppresses_emit(self):
        from behave_retry.hooks import _should_emit_result

        s = FakeScenario("X")
        s.should_run = lambda config=None: False
        assert _should_emit_result(s, FakeRunner()) is False

    def test_show_skipped_overrides(self):
        from behave_retry.hooks import _should_emit_result

        class Cfg:
            show_skipped = True

        s = FakeScenario("X")
        s.should_run = lambda config=None: False
        runner = FakeRunner()
        runner.config = Cfg()
        assert _should_emit_result(s, runner) is True

    def test_should_run_exception_defaults_true(self):
        from behave_retry.hooks import _should_emit_result

        s = FakeScenario("X")

        def boom(config=None):
            raise RuntimeError("x")

        s.should_run = boom
        assert _should_emit_result(s, FakeRunner()) is True


class TestEmitDryRun:
    def test_dry_run_emits_untested_steps(self):
        from behave_retry.hooks import _emit_scenario_result

        emitted = {"match": 0, "result": 0}

        class Fmt:
            def scenario(self, s):
                pass

            def step(self, step):
                pass

            def match(self, m):
                emitted["match"] += 1

            def result(self, r):
                emitted["result"] += 1

        class Registry:
            def find_match(self, step):
                return object()

        s = FakeScenario("X", steps=[FakeStep(status="untested")])
        s.was_dry_run = True
        runner = FakeRunner()
        runner.formatters = [Fmt()]
        runner.step_registry = Registry()
        _emit_scenario_result(s, runner)
        assert emitted["match"] == 1
        assert emitted["result"] == 1

    def test_dry_run_undefined_step_gets_no_result(self):
        """Behave emits no match/result for undefined steps in dry-run."""
        from behave_retry.hooks import _emit_scenario_result

        emitted = {"match": 0, "result": 0}

        class Fmt:
            def scenario(self, s):
                pass

            def step(self, step):
                pass

            def match(self, m):
                emitted["match"] += 1

            def result(self, r):
                emitted["result"] += 1

        class Registry:
            def find_match(self, step):
                return None

        s = FakeScenario("X", steps=[FakeStep(status="undefined")])
        s.was_dry_run = True
        runner = FakeRunner()
        runner.formatters = [Fmt()]
        runner.step_registry = Registry()
        _emit_scenario_result(s, runner)
        assert emitted["match"] == 0
        assert emitted["result"] == 0

    def test_dry_run_untested_without_match_gets_no_result(self):
        """Unresolved untested steps emit nothing in dry-run."""
        from behave_retry.hooks import _emit_scenario_result

        emitted = {"result": 0}

        class Fmt:
            def scenario(self, s):
                pass

            def step(self, step):
                pass

            def result(self, r):
                emitted["result"] += 1

        class Registry:
            def find_match(self, step):
                return None

        s = FakeScenario("X", steps=[FakeStep(status="untested")])
        s.was_dry_run = True
        runner = FakeRunner()
        runner.formatters = [Fmt()]
        runner.step_registry = Registry()
        _emit_scenario_result(s, runner)
        assert emitted["result"] == 0

    def test_non_dry_run_skips_untested_steps(self):
        from behave_retry.hooks import _emit_scenario_result

        emitted = {"result": 0}

        class Fmt:
            def scenario(self, s):
                pass

            def step(self, step):
                pass

            def result(self, r):
                emitted["result"] += 1

        s = FakeScenario("X", steps=[FakeStep(status="untested")])
        runner = FakeRunner()
        runner.formatters = [Fmt()]
        _emit_scenario_result(s, runner)
        assert emitted["result"] == 0


class TestResolveStepMatchRobust:
    def test_registry_keyerror_returns_no_match(self):
        from behave.matchers import NoMatch

        from behave_retry.hooks import _resolve_step_match

        class Registry:
            def find_match(self, step):
                raise KeyError(step.step_type)

        class WeirdStep:
            step_type = "nonexistent_type"

        runner = FakeRunner()
        runner.step_registry = Registry()
        result = _resolve_step_match(runner, WeirdStep())
        assert isinstance(result, NoMatch)


class TestRunQuietReadOnly:
    def test_readonly_formatters_not_suppressed(self):
        from behave_retry.hooks import _run_quiet

        class FrozenRunner:
            @property
            def formatters(self):
                return []

            @formatters.setter
            def formatters(self, v):
                raise AttributeError("read-only")

        ran = []

        def fake_run(self, runner):
            ran.append(1)
            return True

        failed, suppressed = _run_quiet(
            fake_run, FakeScenario("X"), FrozenRunner()
        )
        assert failed is True
        assert suppressed is False
        assert ran == [1]


class TestGetAllStepsCallable:
    def test_all_steps_as_method(self):
        from behave_retry.hooks import _get_all_steps

        step = FakeStep()

        class S(FakeScenario):
            def all_steps(self):
                return [step]

        assert _get_all_steps(S("X")) == [step]


class TestNoMatchTypeFallback:
    def test_returns_none_when_behave_unavailable(self):
        import sys
        from unittest.mock import patch as _patch

        from behave_retry.hooks import _no_match_type

        with _patch.dict(sys.modules, {"behave.matchers": None}):
            assert _no_match_type() is None


class TestSetupRetryEagerResolve:
    def test_invalid_retry_on_string_fails_fast(self):
        ctx = FakeContext()
        with pytest.raises((ImportError, AttributeError, ValueError)):
            setup_retry(ctx, max_retries=1, retry_on=["no.such.module.Nope123"])

    def test_valid_retry_on_string_accepted(self):
        ctx = FakeContext()
        setup_retry(ctx, max_retries=1, retry_on=["ValueError"])
        assert ctx._behave_retry_config.retry_on == ["ValueError"]


class TestPatchedRunEmitGate:
    def test_excluded_scenario_emits_nothing(self):
        """Scenario filtered out by tags must not pollute formatters."""
        calls = {"scenario": 0}

        class Fmt:
            def scenario(self, s):
                calls["scenario"] += 1

        def fake_run(self, runner):
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=1)

            s = FakeScenario("X", status="failed")
            s.should_run = lambda config=None: False
            runner = FakeRunner(ctx)
            runner.formatters = [Fmt()]
            mock_scenario.run(s, runner)

        assert calls["scenario"] == 0

    def test_selected_scenario_emits_once(self):
        calls = {"scenario": 0}

        class Fmt:
            def scenario(self, s):
                calls["scenario"] += 1

        def fake_run(self, runner):
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=2)

            s = FakeScenario("X", status="failed")
            runner = FakeRunner(ctx)
            runner.formatters = [Fmt()]
            mock_scenario.run(s, runner)

        assert calls["scenario"] == 1

    def test_show_skipped_emits_for_excluded(self):
        calls = {"scenario": 0}

        class Fmt:
            def scenario(self, s):
                calls["scenario"] += 1

        class Cfg:
            show_skipped = True

        def fake_run(self, runner):
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=1)

            s = FakeScenario("X", status="failed")
            s.should_run = lambda config=None: False
            runner = FakeRunner(ctx)
            runner.formatters = [Fmt()]
            runner.config = Cfg()
            mock_scenario.run(s, runner)

        assert calls["scenario"] == 1


class TestPatchedRunUnrunnableStats:
    def test_unrunnable_on_retry_records_stats(self):
        """A step turning undefined on the retry must be recorded."""
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                self.steps[0].status = "failed"
                self.steps[0].error = ValueError("x")
            else:
                self.steps[0].status = "undefined"
            self.status = "failed"
            return True

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=3)

            s = FakeScenario("X", steps=[FakeStep()])
            mock_scenario.run(s, FakeRunner(ctx))

        stats = ctx._behave_retry_stats
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 2
        assert stats.scenarios_retried[0].final_status == "failed"


class TestPatchedRunSleepOverflow:
    def test_sleep_overflow_logs_warning_and_continues(self):
        call_count = 0

        def fake_run(self, runner):
            nonlocal call_count
            call_count += 1
            self.status = "failed" if call_count == 1 else "passed"
            return call_count == 1

        ctx = FakeContext()
        with (
            patch("behave.model.Scenario") as mock_scenario,
            patch("behave_retry.hooks.time.sleep", side_effect=OverflowError),
        ):
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=1, retry_delay=1e300)

            s = FakeScenario("X", steps=[FakeStep(error=ValueError("x"))])
            result = mock_scenario.run(s, FakeRunner(ctx))

        assert result is False
        assert call_count == 2


class TestPatchedRunEmitOnInterrupt:
    def test_emit_still_runs_when_attempt_raises(self):
        """Formatter emission must happen even if an attempt propagates."""
        calls = {"scenario": 0}

        class Fmt:
            def scenario(self, s):
                calls["scenario"] += 1

        def fake_run(self, runner):
            raise KeyboardInterrupt

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=2)

            s = FakeScenario("X", status="failed")
            runner = FakeRunner(ctx)
            runner.formatters = [Fmt()]
            with pytest.raises(KeyboardInterrupt):
                mock_scenario.run(s, runner)

        assert calls["scenario"] == 1

    def test_emit_failure_does_not_mask_original_exception(self):
        """A formatter raising during interrupt-emit must not hide it."""

        class BadFmt:
            def scenario(self, s):
                raise RuntimeError("formatter exploded")

        def fake_run(self, runner):
            raise KeyboardInterrupt

        ctx = FakeContext()
        with patch("behave.model.Scenario") as mock_scenario:
            mock_scenario.run = staticmethod(fake_run)
            setup_retry(ctx, max_retries=2)

            s = FakeScenario("X", status="failed")
            runner = FakeRunner(ctx)
            runner.formatters = [BadFmt()]
            with pytest.raises(KeyboardInterrupt):
                mock_scenario.run(s, runner)
