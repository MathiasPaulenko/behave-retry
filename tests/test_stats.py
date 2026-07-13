"""Tests for RetryStats and ScenarioRetry."""

from __future__ import annotations

from behave_retry import RetryStats, ScenarioRetry


class TestScenarioRetry:
    def test_basic(self):
        sr = ScenarioRetry(scenario="Login", attempts=3, final_status="passed")
        assert sr.scenario == "Login"
        assert sr.attempts == 3
        assert sr.final_status == "passed"
        assert sr.was_retried is True
        assert sr.passed_on_retry is True

    def test_no_retry(self):
        sr = ScenarioRetry(scenario="Login", attempts=1, final_status="passed")
        assert sr.was_retried is False
        assert sr.passed_on_retry is False

    def test_failed_after_retry(self):
        sr = ScenarioRetry(scenario="Login", attempts=3, final_status="failed")
        assert sr.was_retried is True
        assert sr.passed_on_retry is False

    def test_with_exceptions(self):
        sr = ScenarioRetry(
            scenario="Login",
            attempts=3,
            final_status="failed",
            exceptions=["AssertionError", "TimeoutError"],
        )
        assert len(sr.exceptions) == 2


class TestRetryStats:
    def test_empty(self):
        stats = RetryStats()
        assert stats.total_retries == 0
        assert stats.scenarios_retried == []
        assert stats.scenarios_passed_on_retry == 0
        assert stats.scenarios_failed_after_retry == 0

    def test_add_retry_passed(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=3, final_status="passed")
        assert stats.total_retries == 2
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_passed_on_retry == 1
        assert stats.scenarios_failed_after_retry == 0

    def test_add_retry_failed(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=3, final_status="failed")
        assert stats.total_retries == 2
        assert stats.scenarios_passed_on_retry == 0
        assert stats.scenarios_failed_after_retry == 1

    def test_add_multiple_retries(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=3, final_status="passed")
        stats.add_retry("Checkout", attempts=2, final_status="failed")
        assert stats.total_retries == 3
        assert len(stats.scenarios_retried) == 2
        assert stats.scenarios_passed_on_retry == 1
        assert stats.scenarios_failed_after_retry == 1

    def test_summary_empty(self):
        stats = RetryStats()
        summary = stats.summary()
        assert "No retries" in summary

    def test_summary_with_retries(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=3, final_status="passed")
        stats.add_retry("Checkout", attempts=2, final_status="failed")
        summary = stats.summary()
        assert "Retry Summary" in summary
        assert "Total retries: 3" in summary
        assert "Login" in summary
        assert "Checkout" in summary
        assert "passed" in summary
        assert "failed" in summary


class TestUpdateRetry:
    def test_update_existing(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="failed")
        stats.update_retry("Login", attempts=3, final_status="failed")
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 3
        assert stats.total_retries == 2

    def test_update_creates_new_if_not_exists(self):
        stats = RetryStats()
        stats.update_retry("Login", attempts=2, final_status="passed")
        assert len(stats.scenarios_retried) == 1
        assert stats.scenarios_retried[0].attempts == 2
        assert stats.scenarios_retried[0].final_status == "passed"

    def test_update_changes_status(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="failed")
        stats.update_retry("Login", attempts=3, final_status="passed")
        assert stats.scenarios_retried[0].final_status == "passed"
        assert stats.scenarios_passed_on_retry == 1
        assert stats.scenarios_failed_after_retry == 0

    def test_update_preserves_other_entries(self):
        stats = RetryStats()
        stats.add_retry("Login", attempts=2, final_status="failed")
        stats.add_retry("Checkout", attempts=1, final_status="failed")
        stats.update_retry("Login", attempts=3, final_status="passed")
        assert len(stats.scenarios_retried) == 2
        assert stats.scenarios_retried[0].scenario == "Login"
        assert stats.scenarios_retried[1].scenario == "Checkout"
