# behave-retry

[![CI](https://github.com/MathiasPaulenko/behave-retry/actions/workflows/ci.yml/badge.svg)](https://github.com/MathiasPaulenko/behave-retry/actions/workflows/ci.yml)
[![Docs](https://github.com/MathiasPaulenko/behave-retry/actions/workflows/docs.yml/badge.svg)](https://mathiaspaulenko.github.io/behave-retry/)
[![PyPI](https://img.shields.io/pypi/v/behave-retry)](https://pypi.org/project/behave-retry/)
[![Python](https://img.shields.io/pypi/pyversions/behave-retry)](https://pypi.org/project/behave-retry/)
[![License](https://img.shields.io/pypi/l/behave-retry)](https://github.com/MathiasPaulenko/behave-retry/blob/main/LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/MathiasPaulenko/behave-retry)

Automatic retry for failed [Behave](https://github.com/behave/behave) scenarios — real re-execution, tag overrides, exception filtering, and flakiness stats.

**[Full documentation →](https://mathiaspaulenko.github.io/behave-retry/)**

## Why?

Behave has no built-in retry. When a scenario fails due to flakiness (timing, network, race conditions), there's no way to re-run it automatically. Cucumber has `--retry` natively. Behave doesn't.

**behave-retry** fills that gap by patching Behave's `Scenario.run` to re-execute failed scenarios automatically — with tag overrides, exception filtering, and flakiness stats.

## Comparison

| Feature | behave-retry | Cucumber `--retry` | pytest-rerunfailures |
|---|---|---|---|
| Per-scenario retry override | `@retry:N` tag | `@retry N` tag | `@pytest.mark.flaky(reruns=N)` |
| Exception filtering | `retry_on=[...]` | No | `reruns_exceptions` |
| Tag filtering | `retry_tags=["@flaky"]` | No | No |
| Global retry budget | `max_total_retries` | No | No |
| Exponential backoff | `retry_delay` + `backoff_factor` | No | `reruns_delay` (fixed) |
| On-retry callback | `on_retry` | No | No |
| Retry stats | Human + JSON | No | No |
| Scenario Outline support | Per-example keys | N/A | N/A |
| Runtime dependencies | Zero | — | pytest plugin |

## Install

```bash
pip install behave-retry
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

- **Global retry** — retry all failed scenarios up to N times
- **Tag-filtered retry** — only retry scenarios with specific tags (`@flaky`)
- **Exception-filtered retry** — only retry on specific exception types or string names
- **Per-scenario override** — `@retry:N` tag overrides global config
- **Feature-level tags** — `@retry:N` on Feature inherits to scenarios
- **Global retry budget** — limit total retries across all scenarios
- **Retry delay and backoff** — configurable delay with exponential backoff
- **On-retry callback** — custom logic before each retry (cleanup, screenshots, etc.)
- **Flakiness stats** — human-readable summary and machine-readable JSON export
- **Scenario Outline support** — unique keys per example, independent retry counts
- **Environment variables** — control retry from `behave-runner` or CI without touching code
- **Logging** — via standard `logging` module under `behave_retry` logger
- **Type-safe** — `py.typed` marker included, full type hints, mypy clean

## Configuration

```python
setup_retry(
    context,
    max_retries=3,              # max retries per scenario
    retry_tags=["@flaky"],      # only retry tagged scenarios
    retry_on=[AssertionError, TimeoutError],  # only retry these exceptions
    retry_delay=2.0,            # 2s delay before first retry
    backoff_factor=2.0,         # double delay each retry (2s, 4s, 8s)
    on_retry=lambda ctx, sc, att, exc: print(f"Retry {sc.name} #{att}: {exc}"),
    max_total_retries=20,       # stop after 20 total retries across all scenarios
)
```

See the [configuration guide](https://mathiaspaulenko.github.io/behave-retry/configuration/) for full details.

## Environment variables

You can control retry behavior via environment variables. This is useful when running tests through `behave-runner`, CI pipelines, or any orchestration tool that passes configuration through the environment.

```python
# environment.py — no hard-coded values
def before_all(context):
    setup_retry(context)
```

```bash
# CLI
BEHAVE_RETRY_MAX_RETRIES=3 BEHAVE_RETRY_DELAY=2.0 BEHAVE_RETRY_BACKOFF=2.0 behave
```

| Env var | Type | Default | Maps to |
|---|---|---|---|
| `BEHAVE_RETRY_MAX_RETRIES` | `int` | `0` | `max_retries` |
| `BEHAVE_RETRY_DELAY` | `float` | `0.0` | `retry_delay` |
| `BEHAVE_RETRY_BACKOFF` | `float` | `1.0` | `backoff_factor` |
| `BEHAVE_RETRY_MAX_TOTAL` | `int` | `None` | `max_total_retries` |

Explicit arguments always win. If you call `setup_retry(context, max_retries=5)`, the env var is ignored.

## How it works

1. `setup_retry` patches `behave.model.Scenario.run` with a retry-aware wrapper.
2. When a scenario fails, the wrapper checks:
   - Does the scenario have retries remaining? (global `max_retries` or `@retry:N` override)
   - Is the scenario tagged for retry? (if `retry_tags` is set)
   - Is the exception type eligible? (if `retry_on` is set)
   - Is the global retry budget exhausted? (if `max_total_retries` is set)
3. If all checks pass, it resets the scenario state and re-runs it.
4. Stats are tracked and available via `retry_report()` or `stats.to_dict()`.

## Documentation

| Section | Description |
|---|---|
| [Installation](https://mathiaspaulenko.github.io/behave-retry/installation/) | Install from PyPI or source |
| [Quick start](https://mathiaspaulenko.github.io/behave-retry/quickstart/) | Three-step setup guide |
| [Features](https://mathiaspaulenko.github.io/behave-retry/features/) | Complete feature walkthrough with examples |
| [Configuration](https://mathiaspaulenko.github.io/behave-retry/configuration/) | All parameters, validation, and precedence rules |
| [Examples](https://mathiaspaulenko.github.io/behave-retry/examples/) | Real-world recipes for common use cases |
| [API reference](https://mathiaspaulenko.github.io/behave-retry/api/setup_retry/) | Full autodoc API |
| [Changelog](https://mathiaspaulenko.github.io/behave-retry/changelog/) | Version history |

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE) — Copyright (c) 2026 Mathias Paulenko
