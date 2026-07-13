# Changelog

All notable changes to this project will be documented in this file.

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
