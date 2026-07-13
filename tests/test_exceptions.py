"""Tests for exceptions."""

from __future__ import annotations

from behave_retry import RetryExhaustedError


class TestRetryExhaustedError:
    def test_message(self):
        err = RetryExhaustedError("Login", attempts=3)
        assert "Login" in str(err)
        assert "3" in str(err)

    def test_attributes(self):
        err = RetryExhaustedError("Checkout", attempts=5)
        assert err.scenario == "Checkout"
        assert err.attempts == 5

    def test_is_exception(self):
        err = RetryExhaustedError("Login", attempts=1)
        assert isinstance(err, Exception)
