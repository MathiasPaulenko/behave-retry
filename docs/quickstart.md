# Quick start

Add retry to your Behave tests in three steps.

## 1. Install

```bash
pip install behave-retry
```

## 2. Configure in `environment.py`

```python
from behave_retry import setup_retry, after_scenario_hook, retry_report

def before_all(context):
    setup_retry(context, max_retries=3)

def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)

def after_all(context):
    print(retry_report(context))
```

### What each function does

| Function | When to call | Purpose |
|---|---|---|
| `setup_retry` | `before_all` | Patches `Scenario.run` with retry logic, stores config on context |
| `after_scenario_hook` | `after_scenario` | Tracks attempt count for backward compatibility |
| `retry_report` | `after_all` | Returns a human-readable summary string of retry stats |

## 3. Run your tests

```bash
behave
```

Failed scenarios will now be re-executed up to 3 times automatically. You'll see output like:

```text
Retry Summary:
  Total retries: 2
  Scenarios retried: 2
  Passed on retry: 1
  Failed after retry: 1

  - "Login with slow network" — 2 attempts, passed
  - "Checkout with expired card" — 4 attempts, failed (AssertionError)
```

## What happens behind the scenes

1. `setup_retry` patches `behave.model.Scenario.run` with a retry-aware wrapper.
2. When a scenario runs and fails, the wrapper checks:
   - Does the scenario have retries remaining? (global `max_retries` or `@retry:N` override)
   - Is the scenario tagged for retry? (if `retry_tags` is set)
   - Is the exception type eligible? (if `retry_on` is set)
   - Is the global retry budget exhausted? (if `max_total_retries` is set)
3. If all checks pass, it resets the scenario state (step statuses, exceptions, error messages) and re-runs it.
4. The retry loop continues until the scenario passes or no more retries remain.
5. Stats are tracked on the context and can be printed with `retry_report`.

## Adding tags for per-scenario control

You can override the global retry count per scenario using the `@retry:N` tag:

```gherkin
@retry:5
Scenario: Very flaky test
  Given a flaky condition
  Then it might fail

@retry:0
Scenario: Never retry this
  Given a stable condition
  Then it should pass
```

## Next steps

- {doc}`features` — explore all available features with examples
- {doc}`configuration` — fine-tune retry behavior with all parameters
- {doc}`examples` — complete real-world recipes
- {doc}`how_it_works` — understand the internal retry loop
