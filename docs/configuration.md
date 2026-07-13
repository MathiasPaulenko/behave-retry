# Configuration

## `setup_retry` parameters

`setup_retry` is the main entry point. It creates a `RetryConfig` and patches `Scenario.run`.

```python
setup_retry(
    context,
    max_retries=3,
    retry_tags=["@flaky"],
    retry_on=[AssertionError, "TimeoutError"],
    retry_delay=2.0,
    backoff_factor=2.0,
    on_retry=on_retry_callback,
    max_total_retries=20,
)
```

### Parameter reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `context` | `Any` | — | Behave context object (required) |
| `max_retries` | `int` | `0` | Maximum retries per scenario (0 = no retry) |
| `retry_tags` | `list[str] \| None` | `None` → `[]` | Only retry scenarios with these tags (empty = retry all) |
| `retry_on` | `list[type[Exception] \| str] \| None` | `None` → `[]` | Only retry on these exception types or names (empty = retry on any) |
| `retry_delay` | `float` | `0.0` | Seconds to wait before each retry (0 = no delay) |
| `backoff_factor` | `float` | `1.0` | Multiplier applied to `retry_delay` after each retry (must be >= 1.0) |
| `on_retry` | `Callable \| None` | `None` | Callback invoked before each retry with `(context, scenario, attempt, exception)` |
| `max_total_retries` | `int \| None` | `None` | Global budget for total retries across all scenarios (None = unlimited) |

## `RetryConfig`

The core configuration dataclass. It is **frozen** (immutable) and validated on creation. You can also construct it directly:

```python
from behave_retry import RetryConfig

config = RetryConfig(
    max_retries=3,
    retry_tags=["@flaky"],
    retry_on=[AssertionError, "TimeoutError"],
    retry_delay=2.0,
    backoff_factor=2.0,
    max_total_retries=20,
)
```

### Methods

| Method | Returns | Description |
|---|---|---|
| `should_retry_tag(tags)` | `bool` | Check if scenario tags allow retry |
| `should_retry_exception(exc)` | `bool` | Check if exception type allows retry |
| `get_scenario_retries(tags, feature_tags=None)` | `int` | Get max retries, checking `@retry:N` on scenario then feature tags |
| `get_retry_delay(attempt)` | `float` | Calculate delay for a given retry attempt (1-based) |

### Validation

`RetryConfig` raises `ValueError` on invalid inputs:

| Condition | Error message |
|---|---|
| `max_retries < 0` | `max_retries must be >= 0, got N` |
| `retry_delay < 0` | `retry_delay must be >= 0, got N` |
| `backoff_factor < 1.0` | `backoff_factor must be >= 1.0, got N` |
| `max_total_retries < 0` (when not `None`) | `max_total_retries must be >= 0 or None, got N` |

```python
from behave_retry import RetryConfig

RetryConfig(max_retries=-1)  # raises ValueError
RetryConfig(retry_delay=-1.0)  # raises ValueError
RetryConfig(backoff_factor=0.5)  # raises ValueError
RetryConfig(max_total_retries=-5)  # raises ValueError
```

Since `RetryConfig` is frozen, attempting to modify an attribute raises `AttributeError`:

```python
config = RetryConfig(max_retries=3)
config.max_retries = 5  # raises AttributeError
```

## Tag override precedence

The `@retry:N` tag is resolved in this order:

1. **Scenario-level** `@retry:N` tag — highest priority
2. **Feature-level** `@retry:N` tag — fallback if scenario has none
3. **Global** `max_retries` from `RetryConfig` — default

```
@retry:3          ← Feature-level
Feature: Example

  Scenario: A     ← No @retry tag → inherits 3 from Feature

  @retry:5
  Scenario: B     ← Scenario-level @retry:5 → overrides to 5

  @retry:0
  Scenario: C     ← Scenario-level @retry:0 → disables retry
```

Negative values from tags are clamped to `0`:

```gherkin
@retry:-5
Scenario: X  # clamped to 0, no retry
```

The first valid `@retry:N` tag wins. Subsequent `@retry:N` tags on the same scenario are ignored:

```gherkin
@retry:3
@retry:5
Scenario: X  # retry:3 wins, retry:5 is ignored
```

## Exception filter resolution

String entries in `retry_on` are resolved to exception classes on first use and cached for subsequent calls:

- **Bare names** (`"AssertionError"`) — looked up in `builtins`
- **Dotted paths** (`"mymod.MyError"`) — split into module path and class name, imported via `importlib`

```python
# These are equivalent:
retry_on=[AssertionError]
retry_on=["AssertionError"]

# Dotted path for custom exceptions:
retry_on=["requests.exceptions.ConnectionError"]
```

### Exception matching

Matching uses `issubclass`, so subclasses of the listed exceptions also match:

```python
class MyTimeoutError(TimeoutError):
    ...

# MyTimeoutError matches because it's a subclass of TimeoutError
setup_retry(context, retry_on=[TimeoutError])
```

### Error handling

- If a string cannot be resolved to an exception class, `ImportError` is raised on first use (not at config time).
- If an entry is neither a class nor a string, `TypeError` is raised.

## Retry delay calculation

The delay for attempt N is:

```
delay = retry_delay * (backoff_factor ** (attempt - 1))
```

| Attempt | `retry_delay=2.0, backoff_factor=2.0` | `retry_delay=1.0, backoff_factor=1.0` | `retry_delay=0.5, backoff_factor=1.5` |
|---|---|---|---|
| 1 | 2.0s | 1.0s | 0.5s |
| 2 | 4.0s | 1.0s | 0.75s |
| 3 | 8.0s | 1.0s | 1.125s |
| 4 | 16.0s | 1.0s | 1.6875s |

If `retry_delay=0.0`, all delays are `0.0` regardless of `backoff_factor`.

## Python version

behave-retry requires **Python 3.11+**.

## Dependencies

Zero required dependencies. `behave` is only needed as a dev dependency for running tests.

## Type checking

behave-retry ships with a `py.typed` marker (since v1.8.0), enabling type checkers like mypy and pyright to recognize type information:

```python
from behave_retry import RetryConfig, RetryStats

config: RetryConfig = RetryConfig(max_retries=3)
# mypy knows the type of config.max_retries is int
```
