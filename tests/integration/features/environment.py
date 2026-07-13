"""Behave environment for integration tests."""

from behave_retry import after_scenario_hook, retry_report, setup_retry


def before_all(context):
    setup_retry(
        context,
        max_retries=2,
        retry_on=[AssertionError],
    )


def after_scenario(context, scenario):
    after_scenario_hook(context, scenario)


def after_all(context):
    context._behave_retry_report = retry_report(context)
