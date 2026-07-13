# behave-retry

[![CI](https://github.com/MathiasPaulenko/behave-retry/actions/workflows/ci.yml/badge.svg)](https://github.com/MathiasPaulenko/behave-retry/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/behave-retry)](https://pypi.org/project/behave-retry/)
[![Python](https://img.shields.io/pypi/pyversions/behave-retry)](https://pypi.org/project/behave-retry/)
[![License](https://img.shields.io/pypi/l/behave-retry)](https://github.com/MathiasPaulenko/behave-retry/blob/main/LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-%3E90%25-brightgreen)](https://github.com/MathiasPaulenko/behave-retry)

Automatic retry for failed [Behave](https://github.com/behave/behave) scenarios — real re-execution, tag overrides, exception filtering, and flakiness stats.

## Why?

Behave has no built-in retry. When a scenario fails due to flakiness (timing, network, race conditions), there's no way to re-run it automatically. Cucumber has `--retry` natively. Behave doesn't.

**behave-retry** fills that gap by patching Behave's `Scenario.run` to re-execute failed scenarios automatically — with tag overrides, exception filtering, and flakiness stats.

## Table of contents

- [Install](#install)
- [Quick start](#quick-start)
- [Features](#features)
  - [Global retry](#global-retry)
  - [Tag-filtered retry](#tag-filtered-retry)
  - [Exception-filtered retry](#exception-filtered-retry)
  - [Per-scenario override](#per-scenario-override)
  - [Retry stats](#retry-stats)
  - [Retry delay and backoff](#retry-delay-and-backoff)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## Install

```bash
pip install behave-retry
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick start

```python
# environment.py
from behave_retry import setup_retry, after_scenario_hook, retry_report

def before_all(context):
    setup_retry(context, max_retries=3)

def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)

def after_all(context):
    print(retry_report(context))
```

That's it. Failed scenarios will now be re-executed up to 3 times automatically.

## Features

### Global retry

```python
setup_retry(context, max_retries=3)
```

Retry every failed scenario up to 3 times.

### Tag-filtered retry

```python
setup_retry(context, max_retries=3, retry_tags=["@flaky"])
```

Only retry scenarios tagged with `@flaky`.

```gherkin
@flaky
Scenario: Login with slow network
  Given the server is slow
  ...
```

### Exception-filtered retry

```python
setup_retry(
    context,
    max_retries=3,
    retry_on=[AssertionError, TimeoutError],
)
```

Only retry when the scenario fails with specific exception types. Subclasses of the listed exceptions also match.

### Per-scenario override

Override the global retry count per scenario using the `@retry:N` tag:

```gherkin
@retry:5
Scenario: Very flaky test
  ...

@retry:0
Scenario: Never retry this
  ...
```

The first `@retry:N` tag wins. `@retry:0` disables retry for that scenario.

### Retry stats

```python
from behave_retry import retry_report

def after_all(context):
    report = retry_report(context)
    print(report)
```

Output:

```text
Retry Summary:
  Total retries: 5
  Scenarios retried: 3
  Passed on retry: 2
  Failed after retry: 1

  - "Login with invalid credentials" — 3 attempts, failed (AssertionError)
  - "Search products" — 2 attempts, passed
  - "Checkout flow" — 2 attempts, passed
```

### Retry delay and backoff

Add a configurable delay between retries, with optional exponential backoff:

```python
setup_retry(
    context,
    max_retries=3,
    retry_delay=2.0,
    backoff_factor=2.0,
)
```

With `retry_delay=2.0` and `backoff_factor=2.0`, delays between retries are 2s, 4s, 8s. With `backoff_factor=1.0` (default), the delay is fixed at `retry_delay` seconds.

## API reference

### `setup_retry(context, max_retries=0, retry_tags=None, retry_on=None, retry_delay=0.0, backoff_factor=1.0)`

Configure retry on the behave context. Call this in `before_all`. This patches `behave.model.Scenario.run` to re-execute failed scenarios automatically.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `context` | `Any` | — | Behave context object |
| `max_retries` | `int` | `0` | Maximum retries per scenario (0 = no retry) |
| `retry_tags` | `list[str] \| None` | `None` | Only retry scenarios with these tags |
| `retry_on` | `list[type[Exception]] \| None` | `None` | Only retry on these exception types |
| `retry_delay` | `float` | `0.0` | Seconds to wait before each retry (0 = no delay) |
| `backoff_factor` | `float` | `1.0` | Multiplier applied to `retry_delay` after each retry (must be >= 1.0) |

### `after_scenario_hook(context, scenario)`

Track retry attempts. Call this in `after_scenario`. The actual retry loop is handled automatically by the `Scenario.run` patch installed by `setup_retry`.

### `retry_report(context) -> str`

Get a human-readable retry summary. Call this in `after_all`.

### `RetryConfig`

Frozen dataclass for configuration.

| Attribute | Type | Default | Description |
|---|---|---|---|
| `max_retries` | `int` | `0` | Maximum retries per scenario (must be >= 0) |
| `retry_tags` | `list[str]` | `[]` | Tag filter (empty = retry all) |
| `retry_on` | `list[type[Exception]]` | `[]` | Exception filter (empty = retry on any) |
| `retry_delay` | `float` | `0.0` | Seconds to wait before each retry (must be >= 0) |
| `backoff_factor` | `float` | `1.0` | Multiplier applied to `retry_delay` (must be >= 1.0) |

Methods:

- `should_retry_tag(tags) -> bool` — Check if scenario tags allow retry
- `should_retry_exception(exc) -> bool` — Check if exception type allows retry
- `get_scenario_retries(tags) -> int` — Get max retries for a scenario, checking `@retry:N` override
- `get_retry_delay(attempt) -> float` — Calculate delay for a given retry attempt (1-based)

### `RetryStats`

Aggregate retry statistics.

| Property | Type | Description |
|---|---|---|
| `total_retries` | `int` | Total retry attempts across all scenarios |
| `scenarios_retried` | `list[ScenarioRetry]` | Per-scenario retry records |
| `scenarios_passed_on_retry` | `int` | Scenarios that passed after retry |
| `scenarios_failed_after_retry` | `int` | Scenarios that still failed after retry |

Methods:

- `add_retry(scenario, attempts, final_status, exceptions) -> None` — Record a new retry
- `update_retry(scenario, attempts, final_status, exceptions) -> None` — Update existing or create new
- `summary() -> str` — Human-readable summary
- `to_dict() -> dict` — Serialize to a dictionary for CI/CD reporting

### `ScenarioRetry`

Record of retry attempts for a single scenario.

| Attribute | Type | Description |
|---|---|---|
| `scenario` | `str` | Scenario name |
| `attempts` | `int` | Total attempts (including first run) |
| `final_status` | `str` | `"passed"` or `"failed"` |
| `exceptions` | `list[str]` | Exception types encountered |

| Property | Description |
|---|---|
| `was_retried` | True if retried at least once |
| `passed_on_retry` | True if passed after retry |

Methods:

- `to_dict() -> dict` — Serialize to a dictionary for CI/CD reporting

### `parse_retry_tag(tags) -> int | None`

Parse `@retry:N` tag from scenario tags. Returns `N` if found, `None` otherwise. Also available as `behave_retry.parse_retry_tag`.

## Configuration

### Python version

behave-retry requires **Python 3.11+**.

### Dependencies

Zero required dependencies. `behave` is only needed as a dev dependency for running tests.

### Linting and formatting

The project uses [Ruff](https://github.com/astral-sh/ruff) with the following rule sets: `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `SIM`.

```bash
ruff check .
```

### Testing

```bash
pytest tests/ -v --cov
```

Coverage threshold is 90%.

## Examples

### Full environment.py

```python
from behave_retry import setup_retry, after_scenario_hook, retry_report

def before_all(context):
    setup_retry(
        context,
        max_retries=3,
        retry_tags=["@flaky"],
        retry_on=[AssertionError, TimeoutError],
        retry_delay=2.0,
        backoff_factor=2.0,
    )

def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)

def after_all(context):
    print(retry_report(context))
```

### Feature file with retry tags

```gherkin
@flaky
@retry:5
Feature: Flaky scenarios

  @retry:0
  Scenario: Never retry this
    Given a stable condition
    Then it should pass

  Scenario: Retry up to 5 times
    Given a flaky condition
    Then it might fail
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE) — Copyright (c) 2026 Mathias Paulenko
