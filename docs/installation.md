# Installation

## From PyPI

```bash
pip install behave-retry
```

## For development

```bash
git clone https://github.com/MathiasPaulenko/behave-retry.git
cd behave-retry
pip install -e ".[dev]"
```

This installs `behave-retry` in editable mode along with development tools:

- `pytest` + `pytest-cov` — testing and coverage
- `ruff` — linting and formatting
- `behave` — for running integration tests

## For documentation

```bash
pip install -e ".[docs]"
```

This installs Sphinx, Furo theme, and MyST parser for building the docs locally:

```bash
python -m sphinx -b html docs/ docs/_build/html
```

Then open `docs/_build/html/index.html` in your browser.

## Requirements

- **Python 3.11+**
- **Zero runtime dependencies** — `behave` is only needed as a dev dependency for running tests

## Verify installation

```python
import behave_retry
print(behave_retry.__version__)
```

## Troubleshooting

### `ImportError: No module named behave`

`behave` is not a runtime dependency of `behave-retry`. Install it separately:

```bash
pip install behave
```

### `setup_retry` has no effect

Make sure you're calling `setup_retry` in `before_all`, not in `before_scenario`. The patch must be applied before any scenario runs.

### Retry not triggering for tagged scenarios

Check that your `retry_tags` configuration matches the tags on your scenarios. Behave strips the leading `@` from tags, but `behave-retry` accepts both `@flaky` and `flaky` in `retry_tags`.

```python
# These are equivalent:
setup_retry(context, retry_tags=["@flaky"])
setup_retry(context, retry_tags=["flaky"])
```

### `py.typed` not found

If your type checker doesn't recognize `behave-retry` types, ensure you're using version 1.8.0+ which includes the `py.typed` marker. Upgrade with:

```bash
pip install --upgrade behave-retry
```
