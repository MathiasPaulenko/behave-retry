"""Tests for RetryConfig."""

from __future__ import annotations

from behave_retry import RetryConfig


class TestRetryConfigDefaults:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_retries == 0
        assert config.retry_tags == []
        assert config.retry_on == []
        assert config.retry_delay == 0.0
        assert config.backoff_factor == 1.0

    def test_negative_max_retries_raises(self):
        import pytest

        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryConfig(max_retries=-1)

    def test_negative_retry_delay_raises(self):
        import pytest

        with pytest.raises(ValueError, match="retry_delay must be >= 0"):
            RetryConfig(retry_delay=-1.0)

    def test_backoff_factor_below_one_raises(self):
        import pytest

        with pytest.raises(ValueError, match="backoff_factor must be >= 1.0"):
            RetryConfig(backoff_factor=0.5)

    def test_frozen(self):
        config = RetryConfig(max_retries=3)
        import pytest

        with pytest.raises(AttributeError):
            config.max_retries = 5


class TestShouldRetryTag:
    def test_no_tag_filter_retries_all(self):
        config = RetryConfig(max_retries=3)
        assert config.should_retry_tag([]) is True
        assert config.should_retry_tag(["@smoke"]) is True

    def test_tag_filter_matches(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag(["@flaky"]) is True
        assert config.should_retry_tag(["@flaky", "@smoke"]) is True

    def test_tag_filter_no_match(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag(["@smoke"]) is False
        assert config.should_retry_tag([]) is False


class TestShouldRetryException:
    def test_no_exception_filter_retries_all(self):
        config = RetryConfig(max_retries=3)
        assert config.should_retry_exception(ValueError) is True
        assert config.should_retry_exception(AssertionError) is True

    def test_exception_filter_matches(self):
        config = RetryConfig(max_retries=3, retry_on=[AssertionError])
        assert config.should_retry_exception(AssertionError) is True

    def test_exception_filter_subclass(self):
        config = RetryConfig(max_retries=3, retry_on=[ValueError])
        assert config.should_retry_exception(KeyError) is False

    def test_exception_filter_no_match(self):
        config = RetryConfig(max_retries=3, retry_on=[AssertionError])
        assert config.should_retry_exception(ValueError) is False


class TestGetScenarioRetries:
    def test_no_tag_override(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([]) == 3
        assert config.get_scenario_retries(["@smoke"]) == 3

    def test_tag_override(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:5"]) == 5
        assert config.get_scenario_retries(["@smoke", "@retry:1"]) == 1

    def test_tag_disable(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:0"]) == 0

    def test_invalid_tag_ignored(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:abc"]) == 3
        assert config.get_scenario_retries(["@retry:"]) == 3

    def test_first_retry_tag_wins(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:2", "@retry:5"]) == 2

    def test_negative_tag_clamped_to_zero(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:-5"]) == 0
        assert config.get_scenario_retries(["retry:-1"]) == 0
