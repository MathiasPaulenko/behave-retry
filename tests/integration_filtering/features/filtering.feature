Feature: Tag and exception filtering for integration testing

  @flaky @retry:3
  Scenario: Flaky scenario with matching tag
    Given a flaky scenario that fails on attempt 1
    Then the scenario should pass on attempt 2

  @smoke @retry:3
  Scenario: Failing scenario with non-matching tag
    Given a scenario that always fails
    Then the scenario should fail

  @retry:0
  Scenario: Scenario with retry disabled
    Given a scenario that always fails
    Then the scenario should fail

  @retry:3
  Scenario: Failing with AssertionError
    Given a scenario that raises AssertionError
    Then the scenario should fail

  @retry:3
  Scenario: Failing with ValueError
    Given a scenario that raises ValueError
    Then the scenario should fail

  @flaky @retry:3
  Scenario: Flaky ValueError scenario that passes on 2nd attempt
    Given a flaky scenario that raises ValueError on attempt 1
    Then the scenario should pass on attempt 2
