# Examples

## Minimal setup

The simplest configuration — retry all failed scenarios up to 3 times:

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

## Environment variables

Control retry from `behave-runner` or CI without touching code:

```python
# environment.py — empty setup reads env vars
def before_all(context):
    setup_retry(context)
```

```bash
# CLI
BEHAVE_RETRY_MAX_RETRIES=3 \
BEHAVE_RETRY_DELAY=2.0 \
BEHAVE_RETRY_BACKOFF=2.0 \
BEHAVE_RETRY_MAX_TOTAL=20 \
behave
```

You can mix env vars with explicit arguments. Explicit arguments always win:

```python
# max_retries is 5 regardless of BEHAVE_RETRY_MAX_RETRIES
def before_all(context):
    setup_retry(context, max_retries=5)
```

## Full `environment.py`

All features enabled:

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
        on_retry=lambda ctx, sc, att, exc: print(f"Retry {sc.name} #{att}: {exc}"),
        max_total_retries=20,
    )

def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)

def after_all(context):
    print(retry_report(context))
```

## Feature file with retry tags

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

## Exception-filtered retry with custom exceptions

Only retry on database or network errors, with a 1s delay and 1.5x backoff:

```python
from myapp.errors import DatabaseError, NetworkError

def before_all(context):
    setup_retry(
        context,
        max_retries=5,
        retry_on=[DatabaseError, NetworkError],
        retry_delay=1.0,
        backoff_factor=1.5,
    )
```

Or using string names (no imports needed):

```python
def before_all(context):
    setup_retry(
        context,
        max_retries=5,
        retry_on=["myapp.errors.DatabaseError", "myapp.errors.NetworkError"],
        retry_delay=1.0,
        backoff_factor=1.5,
    )
```

## Global budget with tag filtering

Limit total retries to 50 across the entire test run, only retrying tagged scenarios:

```python
def before_all(context):
    setup_retry(
        context,
        max_retries=3,
        retry_tags=["@flaky", "@unstable"],
        max_total_retries=50,
    )
```

## On-retry callback with traceback

```python
def on_retry(context, scenario, attempt, exception):
    import traceback
    print(f"Retrying {scenario.name} (attempt {attempt})")
    print(f"  Exception: {exception}")
    if exception:
        traceback.print_exception(
            type(exception), exception, exception.__traceback__
        )

def before_all(context):
    setup_retry(
        context,
        max_retries=3,
        on_retry=on_retry,
    )
```

## On-retry callback with screenshot (Selenium)

```python
def on_retry(context, scenario, attempt, exception):
    if hasattr(context, "driver"):
        filename = f"screenshot_{scenario.name}_{attempt}.png"
        context.driver.save_screenshot(filename)
        print(f"Screenshot saved: {filename}")

def before_all(context):
    setup_retry(
        context,
        max_retries=3,
        on_retry=on_retry,
    )
```

## Dedicated logging handler

```python
import logging

def before_all(context):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[behave-retry] %(message)s"))
    logging.getLogger("behave_retry").addHandler(handler)
    logging.getLogger("behave_retry").setLevel(logging.INFO)
    setup_retry(context, max_retries=3)
```

## Stats for CI/CD reporting

Export retry stats as JSON for CI/CD pipelines:

```python
import json
from behave_retry import retry_report

def after_all(context):
    # Print human-readable summary
    print(retry_report(context))

    # Export machine-readable stats
    stats = getattr(context, "_behave_retry_stats", None)
    if stats:
        with open("retry_report.json", "w") as f:
            json.dump(stats.to_dict(), f, indent=2)
```

The JSON output looks like:

```json
{
  "total_retries": 5,
  "scenarios_retried": [
    {
      "scenario": "Login with invalid credentials",
      "attempts": 3,
      "final_status": "failed",
      "exceptions": ["AssertionError"],
      "was_retried": true,
      "passed_on_retry": false
    },
    {
      "scenario": "Search products",
      "attempts": 2,
      "final_status": "passed",
      "exceptions": ["TimeoutError"],
      "was_retried": true,
      "passed_on_retry": true
    }
  ],
  "scenarios_passed_on_retry": 1,
  "scenarios_failed_after_retry": 1
}
```

## Scenario Outline with retry

Each example in a Scenario Outline gets its own independent retry count:

```gherkin
@flaky
Feature: Login tests

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

With `max_retries=3`:
- "alice" passes on first try → no retry
- "bob" fails → retried up to 3 times independently
- "carol" fails → retried up to 3 times independently

Each example is tracked by `filename:line:name` (e.g. `features/login.feature:5:Login with bob`).

## Conditional retry based on environment

Only retry in CI, not locally:

```python
import os

def before_all(context):
    if os.environ.get("CI"):
        setup_retry(context, max_retries=3, retry_tags=["@flaky"])
    else:
        # No retry in local development
        setup_retry(context, max_retries=0)
```

## Combining with behave's `--tags`

behave-retry works alongside behave's built-in `--tags` filtering. You can use behave to select which scenarios to run, and behave-retry to control retry behavior:

```bash
# Run only @flaky scenarios, retrying up to 3 times
behave --tags=@flaky
```

```python
def before_all(context):
    setup_retry(
        context,
        max_retries=3,
        retry_tags=["@flaky"],
    )
```
