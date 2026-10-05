# How it works

This page explains the internal architecture of behave-retry so you can understand exactly what happens when you call `setup_retry`.

## Architecture overview

behave-retry works by **monkey-patching** `behave.model.Scenario.run` with a retry-aware wrapper. This is the same approach used by behave's own plugin system and is the most reliable way to intercept scenario execution.

```
┌──────────────────────────────────────────────────┐
│                  behave runner                    │
│                                                   │
│  for each scenario:                               │
│    scenario.run(runner)  ← patched by behave-retry│
│      ┌─────────────────────────────────────────┐  │
│      │         patched_run wrapper             │  │
│      │                                          │  │
│      │  1. Load config & stats from context    │  │
│      │  2. Check retry eligibility (tags)      │  │
│      │  3. Call original_run(self, runner)     │  │
│      │  4. If failed → check retry conditions  │  │
│      │  5. If eligible → reset & retry         │  │
│      │  6. Record stats on final attempt       │  │
│      └─────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

## The patch lifecycle

### 1. `setup_retry(context, ...)`

Called in `before_all`. This function:

- Creates a `RetryConfig` dataclass from the provided parameters.
- Creates a `RetryStats` instance for tracking.
- Stores both on the behave `context` object (`_behave_retry_config`, `_behave_retry_stats`, `_behave_retry_attempts`, `_behave_retry_total`).
- Calls `_patch_scenario_run(context)` which:
  - Imports `behave.model.Scenario`.
  - Saves the original `Scenario.run` method.
  - Replaces it with `patched_run` (a closure over `context`).
  - Marks the patch with `_behave_retry_patched = True` to prevent double-patching.

### 2. `patched_run(self, runner)`

Called by behave for every scenario. This is where the retry loop lives.

The wrapper resolves the live context from `runner.context` (falling back to the context captured when the patch was applied). This matters if behave runs more than once in the same process: each run creates a fresh `Context`, and a patch bound permanently to the first context would reuse stale config and stats from the previous run.

Every attempt runs with `runner.formatters` temporarily emptied (formatters would otherwise re-emit the scenario and its steps on each attempt, duplicating report entries). After the last attempt, `_emit_scenario_result` replays the standard event sequence — `scenario()`, `step()` for each step, `match()` + `result()` for each executed step — so reports contain a single entry per scenario with the final outcome. The step match is re-resolved via `runner.step_registry.find_match(step)` because behave does not store it on the step.

#### Step-by-step flow

```
patched_run(scenario, runner)
│
├─ config or stats missing? → delegate to original_run
│
├─ max_for_scenario == 0? → delegate to original_run (no retry)
├─ should_retry_tag(tags) == False? → delegate to original_run
│
├─ attempt = 0
└─ loop:
     ├─ attempt += 1
     ├─ result = original_run(scenario, runner)   ← formatters suppressed
     ├─ store attempt count on context
     │
     ├─ passed? → record stats (if attempt > 1), emit final state, return False
     │
     ├─ failed:
     │   ├─ undefined/pending step? → emit final state, return True
     │   │
     │   ├─ check retry_on filter
     │   │   └─ exception doesn't match? → record stats, return True
     │   │
     │   ├─ check retry limit (attempt > max_for_scenario)
     │   │   └─ exhausted? → record stats, return True
     │   │
     │   ├─ check global budget (max_total_retries)
     │   │   └─ exhausted? → record stats, return True
     │   │
     │   ├─ increment global budget counter
     │   ├─ log retry attempt
     │   ├─ call on_retry callback (if set)
     │   ├─ sleep(delay)
     │   ├─ reset scenario state
     │   └─ continue loop
     │
     └─ on exit: _emit_scenario_result(scenario, runner) — one entry, final state
```

### 3. Scenario state reset

Before each retry, `_reset_scenario_state` is called. This:

- Calls `scenario.clear_status()` (behave's built-in reset) or sets `scenario.status = None` as fallback.
- For each step in the scenario:
  - Calls `step.reset()` if available (behave's built-in step reset).
  - Otherwise sets `step.status = None`.
  - Clears `step.exception`, `step.error_message`, and `step.error` if they exist.

This ensures the scenario starts fresh on each retry — behave won't skip steps that were already "passed" on a previous attempt.

### 4. `after_scenario_hook(context, scenario)`

Called in `after_scenario`. With the patched `Scenario.run`, the retry loop is handled automatically. This hook is kept for backward compatibility and tracks the attempt count on the context for scenarios that were never retried (ensuring every scenario has an entry in `_behave_retry_attempts`).

### 5. `retry_report(context)` and `get_stats(context)`

Called in `after_all`. `retry_report` returns a formatted summary string and logs it at INFO level. `get_stats` returns the `RetryStats` object (or `None`) for programmatic access — e.g. `get_stats(context).to_dict()` for JSON reports.

## Scenario key generation

Each scenario is identified by a unique key stored in `_behave_retry_attempts` and used in `RetryStats`. The key is generated by `_get_scenario_key`:

| Condition | Key format | Example |
|---|---|---|
| `filename`, `line`, and `name` available | `filename:line:name` | `features/login.feature:5:Login with bob` |
| `filename` and `line` available, no `name` | `filename:line` | `features/login.feature:5` |
| Only `name` available | `name` | `Login with bob` |
| Nothing available | `str(scenario)` | `<Scenario object at 0x...>` |

Behave assigns each Scenario Outline example the line of its `Examples` row, so `filename:line` is already unique per example; the name is appended for readability and as a guard for scenarios without line information.

## Exception extraction

When a scenario fails, behave-retry needs to determine what exception caused the failure. Two helpers handle this:

- **`_get_last_exception(scenario)`** — iterates steps in reverse, finds the last failed step with an exception, and returns the exception instance.
- **`_get_last_exception_type(scenario)`** — returns `type(exception)` or `None`.

Both helpers scan `scenario.all_steps`, which includes the per-scenario copies of Background steps — a failure in a `Background` block is therefore visible to `retry_on` filtering.

Behave assigns `Status.failed` to `AssertionError` and `Status.error` to other exceptions. Both are treated as failures by `_step_failed`.

## Idempotency

`_patch_scenario_run` checks for the `_behave_retry_patched` attribute on the original `Scenario.run`. If already patched, it returns immediately. This means calling `setup_retry` multiple times is safe — the second call updates the config on the context but doesn't re-patch.

The closure in `patched_run` reads config dynamically from `runner.context` at call time, so the latest config is always used — even across multiple behave runs in the same process.

## Thread safety

Behave runs scenarios sequentially in a single thread. behave-retry is not designed for concurrent scenario execution and does not use any locking. This is consistent with behave's own execution model.

## Limitations

See {doc}`features` → *Known limitations*. Notably, `before_scenario`/`after_scenario` hooks run per attempt, and formatter output only reflects the final attempt (intermediate attempts are suppressed).
