# Changelog

All notable changes to this project will be documented in this file.

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
- `--retry N` CLI flag support
- `--retry-tags @tag` CLI flag for tag-filtered retry
- `--retry-on ExceptionType` CLI flag for exception-filtered retry
- `@retry:N` tag per scenario for override
- `@retry:0` tag to disable retry for a scenario
- `after_retry` hook support for cleanup between retries
- `RetryExhaustedError` exception
- Zero required dependencies
