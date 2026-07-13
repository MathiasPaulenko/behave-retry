Feature: Flaky scenarios for integration testing

  @retry:3
  Scenario: Flaky scenario that passes on 2nd attempt
    Given a flaky scenario that fails on attempt 1
    Then the scenario should pass on attempt 2

  @retry:2
  Scenario: Always failing scenario
    Given a scenario that always fails
    Then the scenario should fail

  Scenario: Scenario that passes first time
    Given a scenario that always passes
    Then the scenario should pass

  @retry:5
  Scenario: Flaky scenario that passes on 3rd attempt
    Given a flaky scenario that fails on attempts 1 and 2
    Then the scenario should pass on attempt 3
