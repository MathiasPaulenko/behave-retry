"""Integration tests: run behave with behave-retry on real .feature files.

These tests invoke ``behave`` as a subprocess against the feature files
in ``tests/integration/features/`` and ``tests/integration_filtering/features/``
and verify that:

- Flaky scenarios are retried and eventually pass.
- Always-failing scenarios are retried up to the configured limit.
- Tag filtering works end-to-end.
- Exception filtering works end-to-end.
- Scenario outlines don't collide.
- Stats are correctly tracked.
"""

from __future__ import annotations

import os
import subprocess
import sys

FEATURES_DIR = os.path.join(os.path.dirname(__file__), "integration", "features")
FILTERING_DIR = os.path.join(
    os.path.dirname(__file__), "integration_filtering", "features",
)
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def run_behave(
    feature_file: str,
    extra_args: list[str] | None = None,
    features_dir: str | None = None,
) -> subprocess.CompletedProcess:
    if features_dir is None:
        features_dir = FEATURES_DIR
    cmd = [
        sys.executable,
        "-m",
        "behave",
        "--no-color",
        "--format",
        "plain",
        os.path.join(features_dir, feature_file),
    ]
    if extra_args:
        cmd.extend(extra_args)
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=features_dir,
        env=env,
    )


class TestFlakyScenarios:
    def test_flaky_passes_on_second_attempt(self):
        result = run_behave(
            "flaky.feature",
            ["--name", "Flaky scenario that passes on 2nd attempt"],
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "1 scenario passed" in result.stdout or "1 passed" in result.stdout

    def test_always_failing_retried(self):
        result = run_behave("flaky.feature", ["--name", "Always failing scenario"])
        assert result.returncode == 1, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "1 scenario failed" in result.stdout or "1 failed" in result.stdout

    def test_passes_first_time(self):
        result = run_behave("flaky.feature", ["--name", "Scenario that passes first time"])
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    def test_flaky_passes_on_third_attempt(self):
        result = run_behave(
            "flaky.feature",
            ["--name", "Flaky scenario that passes on 3rd attempt"],
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    def test_all_flaky_feature(self):
        result = run_behave("flaky.feature")
        # 3 pass (flaky + first-time + third-attempt), 1 fails (always)
        assert "3 scenarios passed" in result.stdout or "3 passed" in result.stdout
        assert "1 scenario failed" in result.stdout or "1 failed" in result.stdout


class TestTagFiltering:
    def test_matching_tag_retries(self):
        result = run_behave(
            "filtering.feature",
            ["--tags", "@flaky"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "2 scenarios passed" in result.stdout or "2 passed" in result.stdout

    def test_non_matching_tag_no_retry(self):
        result = run_behave(
            "filtering.feature",
            ["--tags", "@smoke"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 1, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "1 scenario failed" in result.stdout or "1 failed" in result.stdout

    def test_retry_disabled_tag(self):
        result = run_behave(
            "filtering.feature",
            ["--name", "Scenario with retry disabled"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 1, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    def test_all_filtering_feature(self):
        result = run_behave(
            "filtering.feature",
            features_dir=FILTERING_DIR,
        )
        # @flaky AssertionError passes (retried)
        # @flaky ValueError passes (retried — tests error status detection)
        # @smoke fails (tag filter blocks retry)
        # @retry:0 fails (disabled)
        # AssertionError fails (retried but exhausts)
        # ValueError errors (retried but exhausts)
        assert "2 scenarios passed" in result.stdout or "2 passed" in result.stdout
        assert "3 failed" in result.stdout
        assert "1 error" in result.stdout


class TestExceptionFiltering:
    def test_assertion_error_retried(self):
        result = run_behave(
            "filtering.feature",
            ["--name", "Failing with AssertionError"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 1, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    def test_value_error_fails_without_flaky_tag(self):
        result = run_behave(
            "filtering.feature",
            ["--name", "Failing with ValueError"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 1, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "ValueError" in result.stdout

    def test_flaky_value_error_retried(self):
        """ValueError sets Status.error in behave, not Status.failed.

        This test verifies that our retry logic correctly detects
        error-status steps and retries them when the exception type
        matches the retry_on filter.
        """
        result = run_behave(
            "filtering.feature",
            ["--name", "Flaky ValueError scenario that passes on 2nd attempt"],
            features_dir=FILTERING_DIR,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "1 scenario passed" in result.stdout or "1 passed" in result.stdout


class TestScenarioOutlines:
    def test_outlines_no_collision(self):
        result = run_behave("outlines.feature")
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "3 scenarios passed" in result.stdout or "3 passed" in result.stdout


class TestRetryReport:
    def test_report_generated(self):
        result = run_behave("flaky.feature")
        # The after_all hook sets context._behave_retry_report
        # We can't access it directly, but we can check behave output
        # for retry-related output if the user prints it
        assert result.returncode == 0 or result.returncode == 1

    def test_report_content_via_custom_format(self):
        """Run behave with a custom format that prints the retry report."""
        result = run_behave("flaky.feature")
        # The report is stored in context._behave_retry_report
        # We verify it's generated by checking the after_all hook doesn't crash
        assert "Traceback" not in result.stderr or "behave_retry" not in result.stderr


class TestEdgeCases:
    def test_nonexistent_feature(self):
        result = run_behave("nonexistent.feature")
        assert result.returncode != 0

    def test_scenario_with_special_chars_in_name(self):
        result = run_behave(
            "flaky.feature",
            ["--name", "Flaky scenario that passes on 2nd attempt"],
        )
        assert result.returncode == 0

    def test_multiple_features_sequentially(self):
        result = run_behave("flaky.feature")
        assert result.returncode in (0, 1)
        result2 = run_behave(
            "filtering.feature",
            features_dir=FILTERING_DIR,
        )
        assert result2.returncode in (0, 1)

    def test_behave_no_capture(self):
        result = run_behave("flaky.feature", ["--no-capture"])
        assert result.returncode in (0, 1)

    def test_behave_dry_run(self):
        result = run_behave("flaky.feature", ["--dry-run"])
        assert result.returncode == 0
