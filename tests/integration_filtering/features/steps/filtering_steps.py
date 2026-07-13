"""Steps for filtering integration tests."""

from behave import given, then

_attempt_counts: dict[str, int] = {}


def _get_attempt(key: str) -> int:
    _attempt_counts[key] = _attempt_counts.get(key, 0) + 1
    return _attempt_counts[key]


@given("a flaky scenario that fails on attempt 1")
def step_flaky_fail_once(context):
    attempts = _get_attempt("flaky_fail_once")
    if attempts < 2:
        raise AssertionError(f"Flaky failure on attempt {attempts}")


@given("a scenario that always fails")
def step_always_fails(context):
    raise AssertionError("Always fails")


@given("a scenario that always passes")
def step_always_passes(context):
    pass


@given("a scenario that raises AssertionError")
def step_raises_assertion(context):
    raise AssertionError("AssertionError")


@given("a scenario that raises ValueError")
def step_raises_value_error(context):
    raise ValueError("ValueError")


@given("a flaky scenario that raises ValueError on attempt 1")
def step_flaky_value_error(context):
    attempts = _get_attempt("flaky_value_error")
    if attempts < 2:
        raise ValueError(f"Flaky ValueError on attempt {attempts}")


@then("the scenario should pass on attempt 2")
def step_pass_on_2(context):
    pass


@then("the scenario should pass")
def step_should_pass(context):
    pass


@then("the scenario should fail")
def step_should_fail(context):
    raise AssertionError("Should fail")
