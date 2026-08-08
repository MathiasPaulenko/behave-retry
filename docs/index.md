# behave-retry

Automatic retry for failed [Behave](https://github.com/behave/behave) scenarios — real re-execution, tag overrides, exception filtering, and flakiness stats.

```{toctree}
:maxdepth: 2
:caption: Getting Started
:hidden:

installation
quickstart
```

```{toctree}
:maxdepth: 2
:caption: Guides
:hidden:

features
configuration
examples
how_it_works
```

```{toctree}
:maxdepth: 2
:caption: API Reference
:hidden:

api/setup_retry
api/after_scenario_hook
api/retry_report
api/RetryConfig
api/RetryStats
api/ScenarioRetry
api/parse_retry_tag
api/types
```

```{toctree}
:maxdepth: 1
:caption: Project
:hidden:

changelog
contributing
```

---

## Overview

Behave has no built-in retry mechanism. When a scenario fails due to flakiness — timing issues, network instability, race conditions — there's no way to re-run it automatically. **behave-retry** fills that gap.

### Key features

- **Global retry** — retry all failed scenarios up to N times
- **Tag-filtered retry** — only retry scenarios with specific tags
- **Exception-filtered retry** — only retry on specific exception types (classes or string names)
- **Per-scenario override** — `@retry:N` tag overrides global config, with Feature-level inheritance
- **Global retry budget** — limit total retries across all scenarios
- **Retry delay and backoff** — configurable delay with exponential backoff
- **On-retry callback** — custom logic before each retry (cleanup, screenshots, logging)
- **Flakiness stats** — human-readable summary and machine-readable JSON export
- **Scenario Outline support** — unique keys per example, independent retry counts
- **Environment variables** — control retry from `behave-runner` or CI without touching code
- **Zero runtime dependencies** — only `behave` needed for development
- **Type-safe** — `py.typed` marker, full type hints, mypy clean

### Quick example

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

### Where to start

- New to behave-retry? Start with the {doc}`installation` and {doc}`quickstart` guides.
- Want to see what it can do? Browse the {doc}`features` page.
- Need detailed parameter info? See the {doc}`configuration` guide.
- Looking for real-world recipes? Check the {doc}`examples` page.
- Want to understand the internals? Read {doc}`how_it_works`.
