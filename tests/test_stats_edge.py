"""Edge case tests for RetryStats and ScenarioRetry."""

from __future__ import annotations

from behave_retry import RetryStats, ScenarioRetry


class TestScenarioRetryEdge:
    def test_zero_attempts(self):
        sr = ScenarioRetry(scenario="X", attempts=0, final_status="failed")
        assert sr.was_retried is False
        assert sr.passed_on_retry is False

    def test_negative_attempts(self):
        sr = ScenarioRetry(scenario="X", attempts=-1, final_status="failed")
        assert sr.was_retried is False

    def test_very_large_attempts(self):
        sr = ScenarioRetry(scenario="X", attempts=999999, final_status="passed")
        assert sr.was_retried is True
        assert sr.passed_on_retry is True

    def test_empty_scenario_name(self):
        sr = ScenarioRetry(scenario="", attempts=2, final_status="passed")
        assert sr.scenario == ""
        assert sr.was_retried is True

    def test_unicode_scenario_name(self):
        sr = ScenarioRetry(scenario="ログイン", attempts=2, final_status="passed")
        assert sr.scenario == "ログイン"

    def test_many_exceptions(self):
        excs = [f"Exc{i}" for i in range(100)]
        sr = ScenarioRetry(scenario="X", attempts=100, final_status="failed", exceptions=excs)
        assert len(sr.exceptions) == 100

    def test_to_dict_includes_key(self):
        sr = ScenarioRetry(scenario="X", attempts=2, final_status="passed", key="file:5")
        d = sr.to_dict()
        assert d["scenario"] == "X"
        assert d["attempts"] == 2
        assert d["final_status"] == "passed"
        assert d["was_retried"] is True
        assert d["passed_on_retry"] is True

    def test_to_dict_exceptions_are_copy(self):
        excs = ["ValueError"]
        sr = ScenarioRetry(scenario="X", attempts=2, final_status="failed", exceptions=excs)
        d = sr.to_dict()
        d["exceptions"].append("NewError")
        assert sr.exceptions == ["ValueError"]

    def test_repr_contains_all_fields(self):
        sr = ScenarioRetry(
            scenario="Login",
            attempts=3,
            final_status="failed",
            exceptions=["AssertionError"],
        )
        r = repr(sr)
        assert "Login" in r
        assert "3" in r
        assert "failed" in r


class TestRetryStatsEdge:
    def test_add_retry_zero_attempts(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=0, final_status="failed")
        assert stats.total_retries == -1
        assert len(stats.scenarios_retried) == 1

    def test_add_retry_one_attempt(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=1, final_status="passed")
        assert stats.total_retries == 0
        assert stats.scenarios_passed_on_retry == 0

    def test_add_retry_with_key(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=2, final_status="passed", key="file:5")
        assert stats.scenarios_retried[0].key == "file:5"

    def test_add_many_retries(self):
        stats = RetryStats()
        for i in range(100):
            stats.add_retry(f"Scenario{i}", attempts=2, final_status="passed")
        assert len(stats.scenarios_retried) == 100
        assert stats.total_retries == 100
        assert stats.scenarios_passed_on_retry == 100

    def test_update_retry_with_key_matching(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=2, final_status="failed", key="file:5")
        stats.update_retry("X", attempts=3, final_status="passed", key="file:5")
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 3
        assert stats.scenarios_retried[0].final_status == "passed"

    def test_update_retry_with_key_no_match_creates_new(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=2, final_status="failed", key="file:5")
        stats.update_retry("X", attempts=3, final_status="passed", key="file:10")
        assert len(stats.scenarios_retried) == 2

    def test_update_retry_no_key_uses_name(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="failed")
        stats.update_retry("Login", attempts=3, final_status="passed")
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 3

    def test_update_retry_different_name_no_key_creates_new(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="failed")
        stats.update_retry("Checkout", attempts=3, final_status="passed")
        assert len(stats.scenarios_retried) == 2

    def test_update_retry_none_exceptions(self):
        stats = RetryStats()
        stats.update_retry("X", attempts=2, final_status="failed", exceptions=None)
        assert stats.scenarios_retried[0].exceptions == []

    def test_summary_with_exceptions(self):
        stats = RetryStats()
        stats.add_retry(
            "Login",
            attempts=3,
            final_status="failed",
            exceptions=["AssertionError", "TimeoutError"],
        )
        summary = stats.summary()
        assert "AssertionError" in summary
        assert "TimeoutError" in summary

    def test_summary_no_exceptions_no_parens(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="passed")
        summary = stats.summary()
        assert "(" not in summary

    def test_to_dict_scenarios_are_copies(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=2, final_status="passed")
        d = stats.to_dict()
        d["scenarios_retried"].append({"fake": True})
        assert len(stats.scenarios_retried) == 1

    def test_to_dict_empty(self):
        stats = RetryStats()
        d = stats.to_dict()
        assert d == {
            "total_retries": 0,
            "scenarios_retried": [],
            "scenarios_passed_on_retry": 0,
            "scenarios_failed_after_retry": 0,
        }

    def test_mixed_passed_and_failed(self):
        stats = RetryStats()
        stats.add_retry("A", attempts=3, final_status="passed")
        stats.add_retry("B", attempts=2, final_status="failed")
        stats.add_retry("C", attempts=4, final_status="passed")
        stats.add_retry("D", attempts=1, final_status="failed")
        assert stats.scenarios_passed_on_retry == 2
        assert stats.scenarios_failed_after_retry == 2
        assert stats.total_retries == 6

    def test_repr_empty(self):
        stats = RetryStats()
        r = repr(stats)
        assert "0" in r

    def test_repr_with_data(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=3, final_status="passed")
        r = repr(stats)
        assert "Login" in r
        assert "3" in r

    def test_update_retry_multiple_times(self):
        stats = RetryStats()
        stats.add_retry("X", attempts=1, final_status="failed")
        stats.update_retry("X", attempts=2, final_status="failed")
        stats.update_retry("X", attempts=3, final_status="failed")
        stats.update_retry("X", attempts=4, final_status="passed")
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 4
        assert stats.scenarios_retried[0].final_status == "passed"
        assert stats.total_retries == 3
