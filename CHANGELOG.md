# Changelog

All notable changes to this project will be documented in this file.

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
