"""Tests for RetryConfig."""

from __future__ import annotations

import pytest

from behave_retry import RetryConfig
from behave_retry.config import _EXCEPTION_CACHE


@pytest.fixture(autouse=True)
def _clear_exception_cache():
    _EXCEPTION_CACHE.clear()
    yield
    _EXCEPTION_CACHE.clear()


class TestRetryConfigDefaults:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_retries == 0
        assert config.retry_tags == []
        assert config.retry_on == []
        assert config.retry_delay == 0.0
        assert config.backoff_factor == 1.0
        assert config.on_retry is None
        assert config.max_total_retries is None

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

    def test_negative_max_total_retries_raises(self):
        with pytest.raises(ValueError, match="max_total_retries must be >= 0 or None"):
            RetryConfig(max_total_retries=-1)

    def test_max_total_retries_zero_allowed(self):
        config = RetryConfig(max_total_retries=0)
        assert config.max_total_retries == 0

    def test_max_total_retries_none_allowed(self):
        config = RetryConfig(max_total_retries=None)
        assert config.max_total_retries is None

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

    def test_string_builtin_exception_matches(self):
        config = RetryConfig(max_retries=3, retry_on=["AssertionError"])
        assert config.should_retry_exception(AssertionError) is True

    def test_string_builtin_exception_no_match(self):
        config = RetryConfig(max_retries=3, retry_on=["ValueError"])
        assert config.should_retry_exception(AssertionError) is False

    def test_string_dotted_exception_matches(self):
        config = RetryConfig(max_retries=3, retry_on=["json.JSONDecodeError"])
        import json

        assert config.should_retry_exception(json.JSONDecodeError) is True

    def test_mixed_class_and_string(self):
        config = RetryConfig(
            max_retries=3, retry_on=[AssertionError, "ValueError"],
        )
        assert config.should_retry_exception(AssertionError) is True
        assert config.should_retry_exception(ValueError) is True
        assert config.should_retry_exception(KeyError) is False

    def test_string_invalid_builtin_raises(self):
        import pytest

        config = RetryConfig(max_retries=3, retry_on=["NotARealException"])
        with pytest.raises(ImportError, match="NotARealException"):
            config.should_retry_exception(AssertionError)

    def test_string_invalid_module_raises(self):
        import pytest

        config = RetryConfig(max_retries=3, retry_on=["nonexistent_module.MyError"])
        with pytest.raises(ImportError):
            config.should_retry_exception(AssertionError)

    def test_string_cached_on_second_call(self):
        from unittest.mock import patch

        config = RetryConfig(max_retries=3, retry_on=["AssertionError"])
        assert config.should_retry_exception(AssertionError) is True
        with patch("behave_retry.config._import_exception") as mock_import:
            assert config.should_retry_exception(AssertionError) is True
            mock_import.assert_not_called()


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


class TestGetScenarioRetriesFeatureTags:
    def test_feature_tag_fallback(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([], feature_tags=["@retry:5"]) == 5

    def test_scenario_tag_takes_precedence_over_feature(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:2"], feature_tags=["@retry:5"]) == 2

    def test_no_feature_tags_uses_global(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([], feature_tags=[]) == 3

    def test_no_feature_tags_param_uses_global(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([]) == 3

    def test_feature_tag_disable(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([], feature_tags=["@retry:0"]) == 0

    def test_scenario_disable_overrides_feature(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@retry:0"], feature_tags=["@retry:5"]) == 0

    def test_invalid_feature_tag_ignored(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries([], feature_tags=["@retry:abc"]) == 3

    def test_feature_tag_with_other_tags(self):
        config = RetryConfig(max_retries=3)
        assert config.get_scenario_retries(["@smoke"], feature_tags=["@flaky", "@retry:7"]) == 7


class TestResolveExceptionFilterEdge:
    """Edge cases for _resolve_exception_filter and _import_exception."""

    def test_resolve_non_exception_class_raises_type_error(self):
        from behave_retry.config import _resolve_exception_filter

        with pytest.raises(TypeError, match="must be an exception class or string"):
            _resolve_exception_filter(int)  # type: ignore[arg-type]

    def test_resolve_non_class_non_string_raises_type_error(self):
        from behave_retry.config import _resolve_exception_filter

        with pytest.raises(TypeError, match="must be an exception class or string"):
            _resolve_exception_filter(42)  # type: ignore[arg-type]

    def test_dotted_path_not_exception_class_raises_import_error(self):
        from behave_retry.config import _import_exception

        with pytest.raises(ImportError, match="is not an exception class"):
            _import_exception("os.path.join")

    def test_dotted_path_nonexistent_module_raises_import_error(self):
        from behave_retry.config import _import_exception

        with pytest.raises(ImportError, match="Cannot import module"):
            _import_exception("nonexistent_module_xyz.SomeError")

    def test_builtin_not_exception_raises_import_error(self):
        from behave_retry.config import _import_exception

        with pytest.raises(ImportError, match="is not a built-in exception class"):
            _import_exception("print")  # type: ignore[arg-type]

    def test_builtin_nonexistent_raises_import_error(self):
        from behave_retry.config import _import_exception

        with pytest.raises(ImportError, match="is not a built-in exception class"):
            _import_exception("NonexistentBuiltinError")


class TestRetryConfigEdge:
    """Edge cases for RetryConfig."""

    def test_get_retry_delay_attempt_zero(self):
        config = RetryConfig(max_retries=3, retry_delay=2.0, backoff_factor=2.0)
        assert config.get_retry_delay(0) == 1.0

    def test_get_retry_delay_negative_attempt(self):
        config = RetryConfig(max_retries=3, retry_delay=2.0, backoff_factor=2.0)
        assert config.get_retry_delay(-1) == 0.5

    def test_get_retry_delay_large_attempt(self):
        config = RetryConfig(max_retries=3, retry_delay=1.0, backoff_factor=2.0)
        assert config.get_retry_delay(10) == 512.0

    def test_should_retry_tag_empty_string_tag(self):
        config = RetryConfig(max_retries=3, retry_tags=["flaky"])
        assert config.should_retry_tag([""]) is False

    def test_should_retry_tag_with_at_prefix_in_retry_tags(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag(["flaky"]) is True

    def test_should_retry_tag_both_with_at_prefix(self):
        config = RetryConfig(max_retries=3, retry_tags=["@flaky"])
        assert config.should_retry_tag(["@flaky"]) is True

    def test_should_retry_exception_subclass_match(self):
        config = RetryConfig(max_retries=3, retry_on=[ValueError])
        assert config.should_retry_exception(KeyError) is False

    def test_should_retry_exception_with_string_and_class_mix(self):
        config = RetryConfig(max_retries=3, retry_on=["ValueError", TypeError])
        assert config.should_retry_exception(ValueError) is True
        assert config.should_retry_exception(TypeError) is True

    def test_parse_retry_tag_empty_string(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag([""]) is None

    def test_parse_retry_tag_retry_no_colon(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag(["retry"]) is None

    def test_parse_retry_tag_retry_empty_value(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag(["retry:"]) is None

    def test_parse_retry_tag_retry_negative(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag(["retry:-1"]) == -1

    def test_parse_retry_tag_multiple_retry_tags(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag(["retry:3", "retry:5"]) == 3

    def test_parse_retry_tag_none_input(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag(None) is None

    def test_parse_retry_tag_empty_list(self):
        from behave_retry.config import parse_retry_tag

        assert parse_retry_tag([]) is None

    def test_max_total_retries_zero_is_valid(self):
        config = RetryConfig(max_retries=3, max_total_retries=0)
        assert config.max_total_retries == 0

    def test_frozen_dataclass_cannot_set_attribute(self):
        config = RetryConfig(max_retries=3)
        with pytest.raises(AttributeError):
            config.max_retries = 5  # type: ignore[misc]

    def test_retry_on_with_invalid_type_raises_on_use(self):
        from behave_retry.config import _resolve_exception_filter

        with pytest.raises(TypeError, match="must be an exception class or string"):
            _resolve_exception_filter(42)
