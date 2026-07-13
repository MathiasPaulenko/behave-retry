"""Edge case tests for RetryConfig and parse_retry_tag."""

from __future__ import annotations

import pytest

from behave_retry import RetryConfig
from behave_retry.config import parse_retry_tag


class TestRetryConfigBoundaries:
    def test_max_retries_zero(self):
        config = RetryConfig(max_retries=0)
        assert config.get_scenario_retries([]) == 0

    def test_max_retries_one(self):
        config = RetryConfig(max_retries=1)
        assert config.get_scenario_retries([]) == 1

    def test_max_retries_very_large(self):
        config = RetryConfig(max_retries=10000)
        assert config.get_scenario_retries([]) == 10000

    def test_negative_one_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryConfig(max_retries=-1)

    def test_very_negative_raises(self):
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryConfig(max_retries=-999)

    def test_frozen_blocks_all_attrs(self):
        config = RetryConfig(max_retries=3)
        with pytest.raises(AttributeError):
            config.max_retries = 5
        with pytest.raises(AttributeError):
            config.retry_tags = ["@flaky"]
        with pytest.raises(AttributeError):
            config.retry_on = [ValueError]

    def test_frozen_blocks_new_attrs(self):
        config = RetryConfig(max_retries=3)
        with pytest.raises(AttributeError):
            config.new_attr = "test"


class TestShouldRetryTagEdge:
    def test_empty_tags_with_empty_filter(self):
        config = RetryConfig(max_retries=3)
        assert config.should_retry_tag([]) is True

    def test_multiple_tags_in_filter(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky", "@smoke"])
        assert config.should_retry_tag(["@flaky"]) is True
        assert config.should_retry_tag(["@smoke"]) is True
        assert config.should_retry_tag(["@flaky", "@smoke"]) is True
        assert config.should_retry_tag(["@regression"]) is False

    def test_tags_with_partial_match(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag(["@smoke", "@flaky", "@regression"]) is True

    def test_empty_scenario_tags_with_filter(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag([]) is False


class TestShouldRetryExceptionEdge:
    def test_custom_exception_subclass(self):
        class MyError(ValueError):
            pass

        config = RetryConfig(max_retries=3, retry_on=[ValueError])
        assert config.should_retry_exception(MyError) is True

    def test_base_exception_not_matched(self):
        config = RetryConfig(max_retries=3, retry_on=[ValueError])
        assert config.should_retry_exception(Exception) is False

    def test_multiple_exception_types(self):
        config = RetryConfig(max_retries=3, retry_on=[ValueError, TypeError])
        assert config.should_retry_exception(ValueError) is True
        assert config.should_retry_exception(TypeError) is True
        assert config.should_retry_exception(KeyError) is False

    def test_exception_hierarchy(self):
        class CustomBaseError(Exception):
            pass

        class MidLevelError(CustomBaseError):
            pass

        class DeepLevelError(MidLevelError):
            pass

        config = RetryConfig(max_retries=3, retry_on=[CustomBaseError])
        assert config.should_retry_exception(MidLevelError) is True
        assert config.should_retry_exception(DeepLevelError) is True


class TestGetScenarioRetriesEdge:
    def test_override_to_zero_disables(self):
        config = RetryConfig(max_retries=5)
        assert config.get_scenario_retries(["@retry:0"]) == 0

    def test_override_to_one(self):
        config = RetryConfig(max_retries=5)
        assert config.get_scenario_retries(["@retry:1"]) == 1

    def test_override_higher_than_global(self):
        config = RetryConfig(max_retries=2)
        assert config.get_scenario_retries(["@retry:10"]) == 10

    def test_override_with_other_tags(self):
        config = RetryConfig(max_retries=2)
        assert config.get_scenario_retries(["@smoke", "@regression", "@retry:7"]) == 7

    def test_multiple_retry_tags_first_wins(self):
        config = RetryConfig(max_retries=2)
        assert config.get_scenario_retries(["@retry:3", "@retry:5"]) == 3

    def test_invalid_override_falls_back(self):
        config = RetryConfig(max_retries=4)
        assert config.get_scenario_retries(["@retry:abc"]) == 4
        assert config.get_scenario_retries(["@retry:"]) == 4

    def test_negative_override(self):
        config = RetryConfig(max_retries=4)
        assert config.get_scenario_retries(["@retry:-1"]) == 0

    def test_empty_string_tag(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([""]) == 3

    def test_tag_with_whitespace(self):
        config = RetryConfig(max_retries=3)
        result = config.get_scenario_retries(["@retry:3 "])
        assert result == 3


class TestParseRetryTagEdge:
    def test_empty_list(self):
        assert parse_retry_tag([]) is None

    def test_none_tags(self):
        assert parse_retry_tag(None) is None  # type: ignore[arg-type]

    def test_tag_with_extra_colon(self):
        result = parse_retry_tag(["@retry:3:extra"])
        assert result == 3

    def test_tag_with_whitespace(self):
        assert parse_retry_tag([" @retry:3"]) is None
        assert parse_retry_tag(["@retry:3 "]) == 3

    def test_tag_case_sensitive(self):
        assert parse_retry_tag(["@Retry:3"]) is None
        assert parse_retry_tag(["@RETRY:3"]) is None

    def test_tag_without_at_prefix(self):
        assert parse_retry_tag(["retry:3"]) == 3

    def test_tag_with_double_at_prefix_not_parsed(self):
        assert parse_retry_tag(["@@retry:3"]) is None

    def test_tag_with_negative_number(self):
        assert parse_retry_tag(["@retry:-5"]) == -5

    def test_tag_with_float(self):
        result = parse_retry_tag(["@retry:3.5"])
        assert result is None

    def test_tag_with_very_large_number(self):
        assert parse_retry_tag(["@retry:999999999"]) == 999999999

    def test_tag_is_only_prefix(self):
        assert parse_retry_tag(["@retry:"]) is None

    def test_tag_is_only_prefix_no_colon(self):
        assert parse_retry_tag(["@retry"]) is None

    def test_multiple_invalid_before_valid(self):
        assert parse_retry_tag(["@retry:abc", "@retry:", "@retry:5"]) == 5

    def test_valid_tag_not_first(self):
        assert parse_retry_tag(["@smoke", "@regression", "@retry:2"]) == 2


class TestGetRetryDelay:
    def test_zero_delay_returns_zero(self):
        config = RetryConfig(max_retries=3, retry_delay=0.0)
        assert config.get_retry_delay(1) == 0.0
        assert config.get_retry_delay(5) == 0.0

    def test_base_delay_no_backoff(self):
        config = RetryConfig(max_retries=3, retry_delay=2.0, backoff_factor=1.0)
        assert config.get_retry_delay(1) == 2.0
        assert config.get_retry_delay(2) == 2.0
        assert config.get_retry_delay(3) == 2.0

    def test_delay_with_backoff(self):
        config = RetryConfig(max_retries=3, retry_delay=1.0, backoff_factor=2.0)
        assert config.get_retry_delay(1) == 1.0
        assert config.get_retry_delay(2) == 2.0
        assert config.get_retry_delay(3) == 4.0
        assert config.get_retry_delay(4) == 8.0

    def test_delay_with_fractional_backoff(self):
        config = RetryConfig(max_retries=3, retry_delay=0.5, backoff_factor=1.5)
        assert config.get_retry_delay(1) == 0.5
        assert config.get_retry_delay(2) == 0.75
        assert config.get_retry_delay(3) == 1.125

    def test_delay_zero_with_backoff_returns_zero(self):
        config = RetryConfig(max_retries=3, retry_delay=0.0, backoff_factor=2.0)
        assert config.get_retry_delay(1) == 0.0
        assert config.get_retry_delay(10) == 0.0

    def test_delay_large_backoff_factor(self):
        config = RetryConfig(max_retries=3, retry_delay=0.1, backoff_factor=10.0)
        assert config.get_retry_delay(1) == 0.1
        assert config.get_retry_delay(2) == 1.0
        assert config.get_retry_delay(3) == 10.0
