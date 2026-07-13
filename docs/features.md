# Features

## Global retry

Retry every failed scenario up to N times:

```python
setup_retry(context, max_retries=3)
```

With `max_retries=3`, a scenario gets up to 4 total executions (1 initial + 3 retries). Set `max_retries=0` (default) to disable retry entirely.

## Tag-filtered retry

Only retry scenarios with specific tags:

```python
setup_retry(context, max_retries=3, retry_tags=["@flaky"])
```

```gherkin
@flaky
Scenario: Login with slow network
  Given the server is slow
  ...
```

Multiple tags work as OR — a scenario needs at least one matching tag to be eligible:

```python
setup_retry(context, max_retries=3, retry_tags=["@flaky", "@unstable"])
```

Behave strips the leading `@` from tags, so both `@flaky` and `flaky` are accepted in `retry_tags`.

## Exception-filtered retry

Only retry when the scenario fails with specific exception types. Subclasses also match:

```python
setup_retry(
    context,
    max_retries=3,
    retry_on=[AssertionError, TimeoutError],
)
```

String names are also supported — useful for configuration files or when you want to avoid importing the exception class:

```python
setup_retry(
    context,
    max_retries=3,
    retry_on=["AssertionError", "mymod.MyError"],
)
```

Dotted paths are resolved via `importlib`:

```python
setup_retry(
    context,
    max_retries=3,
    retry_on=["requests.exceptions.ConnectionError"],
)
```

### How exception filtering interacts with retries

When `retry_on` is set and a scenario fails:

1. The wrapper extracts the exception type from the last failed step.
2. If the exception type matches any entry in `retry_on` (via `issubclass`), the scenario is retried.
3. If the exception type does **not** match, the scenario fails immediately — no retry.
4. If no exception can be found on the failed step (e.g. behave didn't attach one), the scenario is **not** retried.

## Per-scenario override

Override the global retry count per scenario using the `@retry:N` tag:

```gherkin
@retry:5
Scenario: Very flaky test
  ...

@retry:0
Scenario: Never retry this
  ...
```

The first `@retry:N` tag wins. `@retry:0` disables retry for that scenario. Negative values are clamped to `0`.

### Feature-level tags

Set `@retry:N` at the **Feature level** — scenarios without their own `@retry:N` tag inherit it:

```gherkin
@retry:3
Feature: Flaky scenarios

  Scenario: A  # inherits retry:3
    ...

  @retry:0
  Scenario: B  # override local, no retry
    ...

  @retry:5
  Scenario: C  # override local, retry 5
    ...
```

Scenario-level tags always take precedence over Feature-level tags. See {doc}`configuration` for the full precedence rules.

## Global retry budget

Limit the total number of retries across all scenarios:

```python
setup_retry(context, max_retries=5, max_total_retries=20)
```

Once the global budget is exhausted, no more retries are attempted — remaining scenarios run only once. `None` (default) means unlimited.

The budget is shared across all scenarios in the test run. Each retry decrements the budget by 1. When the budget reaches 0, the current scenario fails immediately and no further retries are attempted on any scenario.

```python
# With max_total_retries=2:
# Scenario A fails → retry 1 (budget: 1)
# Scenario A fails → retry 2 (budget: 0)
# Scenario A fails → no more retries, fails
# Scenario B fails → budget exhausted, no retry, fails immediately
```

## Retry delay and backoff

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

The delay is calculated as:

```
delay = retry_delay * (backoff_factor ** (attempt - 1))
```

If `retry_delay=0.0` (default), no delay is applied regardless of `backoff_factor`.

## On-retry callback

Run custom logic before each retry — clean up state, take screenshots, log, etc.:

```python
def on_retry(context, scenario, attempt, exception):
    print(f"Retrying {scenario.name} (attempt {attempt}): {exception}")

setup_retry(
    context,
    max_retries=3,
    on_retry=on_retry,
)
```

The callback receives `(context, scenario, attempt, exception)`:

| Parameter | Type | Description |
|---|---|---|
| `context` | `Any` | Behave context object |
| `scenario` | `Any` | Behave scenario object that failed |
| `attempt` | `int` | 1-based number of the failed attempt |
| `exception` | `Exception \| None` | Exception that caused the failure, or `None` |

The callback is called **before** the delay and scenario reset, so you can inspect the failed state.

## Logging

behave-retry logs via the standard `logging` module under the `behave_retry` logger:

- **INFO** on `setup_retry` — configuration summary
- **INFO** on each retry — `Retrying "scenario name" (attempt 1/3) after AssertionError`
- **INFO** on `retry_report` — full summary

```python
import logging

def before_all(context):
    logging.basicConfig(level=logging.INFO)
    setup_retry(context, max_retries=3)
```

Or use a dedicated handler with custom formatting:

```python
import logging

def before_all(context):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[behave-retry] %(message)s"))
    logging.getLogger("behave_retry").addHandler(handler)
    logging.getLogger("behave_retry").setLevel(logging.INFO)
    setup_retry(context, max_retries=3)
```

## Retry stats

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

### Machine-readable stats

For CI/CD integration, export stats as JSON:

```python
import json

def after_all(context):
    stats = getattr(context, "_behave_retry_stats", None)
    if stats:
        with open("retry_report.json", "w") as f:
            json.dump(stats.to_dict(), f, indent=2)
```

See {doc}`api/RetryStats` and {doc}`api/ScenarioRetry` for the full API.

## Scenario Outline support

Scenario Outline examples are uniquely identified by `filename:line:name`, preventing key collisions between examples that share the same file and line but have different names after placeholder substitution.

```gherkin
Scenario Outline: Login with <user>
  Given a user "<user>"
  When they log in with password "<pass>"
  Then the login should <result>

Examples:
  | user  | pass      | result       |
  | alice | secret123 | succeed      |
  | bob   | wrong     | fail         |
  | carol | expired   | fail         |
```

Each example gets its own independent retry count. If "alice" passes on the first try but "bob" fails and is retried, only "bob" consumes retry budget.

## Combining features

All features can be combined. The retry decision flow for a failed scenario is:

1. **Retry count check** — `max_for_scenario == 0`? → no retry
2. **Tag filter check** — `retry_tags` set and scenario doesn't match? → no retry
3. **Run scenario** — if it passes, done
4. **Exception filter check** — `retry_on` set and exception doesn't match? → no retry, fail
5. **Retry limit check** — `attempt > max_for_scenario`? → no retry, fail
6. **Budget check** — `max_total_retries` set and budget exhausted? → no retry, fail
7. **Retry** — increment budget, call `on_retry`, sleep `delay`, reset state, go to step 3
