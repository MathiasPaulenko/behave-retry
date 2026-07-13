# behave-retry

Automatic retry for failed Behave scenarios.

## Why?

Behave has no built-in retry. When a scenario fails due to flakiness (timing, network, race conditions), there's no way to re-run it automatically. Cucumber has `--retry` natively. Behave doesn't.

## Install

```bash
pip install behave-retry
```

## Quick start

```python
# environment.py
from behave_retry import setup_retry, after_scenario_hook

def before_all(context):
    setup_retry(context, max_retries=3)

def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)

def after_all(context):
    from behave_retry import retry_report
    print(retry_report(context))
```

## Features

### Global retry

```bash
behave --retry 3
```

Retry every failed scenario up to 3 times.

### Tag-filtered retry

```bash
behave --retry 3 --retry-tags @flaky
```

Only retry scenarios tagged with `@flaky`.

### Exception-filtered retry

```bash
behave --retry 3 --retry-on AssertionError --retry-on TimeoutError
```

Only retry when the scenario fails with specific exception types.

### Per-scenario override

```gherkin
@retry:5
Scenario: Very flaky test
  ...

@retry:0
Scenario: Never retry this
  ...
```

### Cleanup between retries

```python
# environment.py
def after_retry(context, scenario):
    # Close browser, reset DB, clean state
    if hasattr(context, "driver"):
        context.driver.quit()
```

### Retry stats

```python
from behave_retry import retry_report

def after_all(context):
    report = retry_report(context)
    print(report)
    # Retry Summary:
    #   Total retries: 5
    #   Scenarios retried: 3
    #   Passed on retry: 2
    #   Failed after retry: 1
    #   - "Login with invalid credentials" — 3 attempts, failed (AssertionError)
    #   - "Search products" — 2 attempts, passed
    #   - "Checkout flow" — 1 attempt, passed
```

## API

| Function | Description |
|---|---|
| `setup_retry(context, max_retries, retry_tags, retry_on)` | Configure retry in `before_all` |
| `after_scenario_hook(context, scenario)` | Call in `after_scenario` to handle retry logic |
| `retry_report(context)` | Get human-readable retry summary |
| `RetryStats` | Dataclass with retry statistics |

## Zero dependencies

`behave-retry` has no required dependencies beyond behave itself.

## License

MIT
