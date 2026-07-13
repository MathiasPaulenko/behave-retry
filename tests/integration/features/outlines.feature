Feature: Scenario outlines for collision testing

  @retry:2
  Scenario Outline: Flaky outline scenario
    Given a flaky scenario with name <name>
    Then the scenario should pass on attempt 2

    Examples:
      | name  |
      | Alpha |
      | Beta  |
      | Gamma |
