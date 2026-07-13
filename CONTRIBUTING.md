# Contributing to behave-retry

Thank you for your interest in contributing to behave-retry! This document
covers everything you need to know to get started.

## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) or pip
- Git

## Getting started

```bash
git clone https://github.com/MathiasPaulenko/behave-retry.git
cd behave-retry
pip install -e ".[dev]"
```

Verify your setup:

```bash
ruff check .
pytest tests/ -v
```

## Development workflow

### 1. Create a branch

```bash
git checkout -b feat/my-feature
```

Use the following prefixes:

- `feat/` — new features
- `fix/` — bug fixes
- `docs/` — documentation changes
- `refactor/` — code refactoring
- `test/` — test additions or fixes
- `chore/` — tooling, CI, dependencies

### 2. Make your changes

- Follow the existing code style. Ruff enforces it automatically.
- Keep functions small and focused (single responsibility).
- Use type hints on all parameters and return types.
- Write docstrings in Google or NumPy format.
- Add or update tests for any changed behavior.

### 3. Run checks locally

```bash
ruff check .
pytest tests/ -v --cov
```

Both must pass before opening a PR. Coverage must stay at or above 90%.

### 4. Commit your changes

Write clear, concise commit messages. Use the imperative mood:

```text
Add exception filtering to retry config
Fix off-by-one in retry attempt counter
Update README with API reference table
```

### 5. Open a pull request

Push your branch and open a PR against `main`. Fill in the PR template and
link any related issues.

## Code style

This project uses [Ruff](https://github.com/astral-sh/ruff) with the following
rule sets: `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `SIM`.

Key conventions:

- Line length: 100 characters
- Import sorting: `isort`-compatible (first-party: `behave_retry`)
- Use `from __future__ import annotations` in all modules
- Prefer dataclasses for structured data
- No comments that don't add value

## Testing

Tests live in `tests/` and use `pytest`. The project uses fake objects
(`FakeScenario`, `FakeContext`) to test hooks without a real Behave runner.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov

# Run a single test file
pytest tests/test_config.py -v
```

## Pull request guidelines

- One feature or fix per PR.
- Include tests for any new behavior.
- Keep PRs small and focused for easier review.
- Update the CHANGELOG.md under an `## [Unreleased]` section.
- Ensure CI passes: `ruff check .` and `pytest tests/ -v --cov`.

## Reporting bugs

Open a [bug report issue](https://github.com/MathiasPaulenko/behave-retry/issues/new?template=bug_report.md)
and include:

- Python version
- behave-retry version
- Minimal reproduction steps
- Expected vs actual behavior

## Suggesting features

Open a [feature request issue](https://github.com/MathiasPaulenko/behave-retry/issues/new?template=feature_request.md)
and describe:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Release process

Releases are automated through GitHub Actions:

1. Update `version` in `pyproject.toml` and `__version__` in `__init__.py`.
2. Update `CHANGELOG.md` with the new version and date.
3. Tag the commit: `git tag v1.x.x`.
4. Push the tag: `git push origin v1.x.x`.
5. CI builds the package and publishes to PyPI via trusted publishing (OIDC).

## Questions?

Open a [discussion](https://github.com/MathiasPaulenko/behave-retry/discussions)
or an issue. We're happy to help.
