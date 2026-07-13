# Changelog

All notable changes to this project will be documented in this file.

## [1.4.0] - 2026-07-13

### Added

- `on_retry` callback parameter in `RetryConfig` and `setup_retry` — invoked before each retry with `(context, scenario, attempt, exception)`
- `RetryCallback` type alias exported from the package
- `_get_last_exception` helper to retrieve the exception instance from a failed scenario
- 8 new tests for `on_retry` callback behavior (called on retry, each retry, not called without callback, not called on pass, None exception, called before delay, stored in config)
- `retry_on` now accepts string exception names in addition to classes — e.g. `["AssertionError", "json.JSONDecodeError"]`
- `ExceptionFilter` type alias exported from the package
- `_resolve_exception_filter` and `_import_exception` helpers for resolving string names to exception classes with caching
- 8 new tests for string-based exception filtering (builtin match, builtin no-match, dotted path, mixed class+string, invalid builtin, invalid module, cache verification)

## [1.3.0] - 2026-07-13

### Added

- `py.typed` marker file for PEP 561 type-checker support
- `force-include` in `pyproject.toml` to ensure `py.typed` is packaged in the wheel
- `retry_delay` and `backoff_factor` parameters to `RetryConfig` and `setup_retry` — configurable delay between retries with exponential backoff
- `RetryConfig.get_retry_delay(attempt)` method — calculates the delay for a given retry attempt number
- Validation for `retry_delay` (must be >= 0) and `backoff_factor` (must be >= 1.0) in `RetryConfig.__post_init__`
- 10 new tests: 6 for `get_retry_delay` (zero, fixed, backoff, fractional, large factor, zero-with-backoff), 4 for `patched_run` delay behavior (no-delay, fixed, backoff, delay-only-before-retry)

## [1.2.0] - 2026-07-13

### Added

- Google-style docstrings (`Args`, `Returns`, `Raises`, `Attributes`) on all public and internal functions, methods, properties, and classes
- `patched_run` inner function now has a full docstring
- `__post_init__` now has a docstring with `Raises` section
- `scenarios_passed_on_retry` and `scenarios_failed_after_retry` properties now have docstrings
- Test: `test_tag_with_double_at_prefix_not_parsed` — verifies `@@retry:3` is rejected
- Test: `test_reset_scenario_state_no_clear_status` — verifies fallback when scenario lacks `clear_status()`
- Test: `test_patched_run_without_config_falls_back` — verifies graceful degradation when context loses config
- Test: `test_patched_run_without_stats_falls_back` — verifies graceful degradation when context loses stats
- Test: `test_negative_tag_clamped_to_zero` — verifies negative `@retry:N` tags are clamped to 0
- Test: `test_setup_retry_updates_config_after_repatch` — verifies re-calling `setup_retry` with new config takes effect
- Test: `test_flaky_value_error_retried` — integration test for `ValueError` with `Status.error`
- Integration feature: `Flaky ValueError scenario that passes on 2nd attempt` for error-status retry testing

### Fixed

- `lstrip("@")` replaced with `removeprefix("@")` in `parse_retry_tag` and `should_retry_tag` — `lstrip` stripped all leading `@` characters, so `@@retry:3` was incorrectly parsed as valid
- `_reset_scenario_state` now guards `clear_status()` with `hasattr` — falls back to `scenario.status = None` instead of crashing with `AttributeError`
- `patched_run` now reads `config` and `stats` from `context` at runtime via `getattr` instead of capturing them in the closure — prevents stale references when `setup_retry` is called multiple times
- `patched_run` gracefully delegates to `original_run` if `_behave_retry_config` or `_behave_retry_stats` are missing from context
- Negative `@retry:N` tag values are now clamped to 0 via `max(0, override)` in `get_scenario_retries`
- `_step_failed` helper now detects both `"failed"` and `"error"` step statuses — Behave assigns `Status.error` to non-`AssertionError` exceptions
- `after_scenario_hook` uses `getattr` for `_behave_retry_attempts` — prevents `AttributeError` if attribute is missing
- Patch idempotency: `patched_run` is marked with `_behave_retry_patched = True` to prevent double-wrapping `Scenario.run` on repeated `setup_retry` calls
- `ValueError` added to `retry_on` in filtering integration tests to test `Status.error` handling end-to-end

### Changed

- `RetryStats.update_retry` calculates `match_key` outside the loop for minor performance improvement
- Removed dead code: `_should_retry_scenario` function and `reset_attempts` in `flaky_steps.py`
- Renamed `test_value_error_not_retried` to `test_value_error_fails_without_flaky_tag` for clarity
- Updated `test_all_filtering_feature` assertions to reflect new scenario counts
- Updated `test_matching_tag_retries` to expect 2 passed scenarios (both `@flaky` tags)

## [1.1.0] - 2026-07-13

### Added

- **Real retry**: `setup_retry` now patches `behave.model.Scenario.run` to re-execute failed scenarios automatically
- `parse_retry_tag` moved to `config.py` and unified with `get_scenario_retries` — single source of truth for `@retry:N` parsing
- `parse_retry_tag` exported from top-level package

### Fixed

- `_get_scenario_key` no longer uses `Feature` object as fallback — only uses `filename` (string) or scenario name
- `pyproject.toml` description no longer mentions non-existent CLI flags
- `after_scenario_hook` docstring no longer references non-existent CLI flags
- README example output fixed: scenarios with 1 attempt are not "retried"

### Changed

- `after_scenario_hook` is now backward-compatible — the retry loop is handled by the patched `Scenario.run`, the hook only tracks attempts
- Version bumped to 1.1.0 (minor: new feature — real retry)

## [1.0.2] - 2026-07-13

### Fixed

- Scenario collision fixed — uses `filename:line` as unique key instead of name
- `parse_retry_tag` now delegates to `RetryConfig.get_scenario_retries` to avoid duplicated logic

### Changed

- `RetryConfig` is now a frozen dataclass (immutable)
- `max_retries` validation: raises `ValueError` if negative
- Removed unused `RetryExhaustedError` exception and `exceptions.py` module
- README and CHANGELOG corrected: removed references to non-existent CLI flags and `after_retry` hook

### Added

- `RetryStats.to_dict()` and `ScenarioRetry.to_dict()` for CI/CD reporting
- `__repr__` on `RetryStats` and `ScenarioRetry` (via dataclass)

## [1.0.1] - 2026-07-13

### Fixed

- Exception filtering (`retry_on`) now actually works — `should_retry_exception` is called in `after_scenario_hook`
- Stats no longer duplicate entries per attempt — `update_retry` updates a single record per scenario
- `total_retries` correctly counts retries (attempts - 1) instead of inflating with duplicate entries
- Exception type names are now captured from failed steps instead of always being empty
- Removed broken `_get_last_exception()` function
- Removed dead code in `_get_scenario_tags()` (loop with `pass` body)

### Added

- `RetryStats.update_retry()` — update an existing retry record or create a new one
- `_get_step_status()`, `_get_scenario_exceptions()`, `_get_last_exception_type()` helper functions
- 9 new tests covering exception filtering, stats deduplication, and step exception capture

## [1.0.0] - 2026-07-13

### Added

- `setup_retry()` — configure retry in `before_all` hook
- `after_scenario_hook()` — handle retry logic in `after_scenario`
- `retry_report()` — human-readable retry summary
- `RetryStats` and `ScenarioRetry` dataclasses for stats tracking
- `RetryConfig` dataclass for configuration
- `@retry:N` tag per scenario for override
- `@retry:0` tag to disable retry for a scenario
- Zero required dependencies
