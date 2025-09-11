# Contributing

Thanks for your interest in contributing to CogMyra!

## Getting Started

- Install dependencies with `poetry install` (Python 3.11+).
- Run linters and tests: `poetry run ruff check .`, `poetry run ruff format --check .`, `poetry run pytest -q`.

## Guidelines

- Keep PRs small, focused, and well-tested.
- Add or update tests for any functional change.
- Follow the existing style; prefer type hints and docstrings for public functions.

## Pre-commit

Optionally enable pre-commit hooks:

```
poetry run pre-commit install
```

This will run Ruff checks and formatting on commit.

