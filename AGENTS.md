# Agent Guidelines for CogMyra

This repository is set up for agent-assisted development. Please follow these guidelines when working on tasks:

## Scope

- Use the `src/` layout: all Python packages live under `src/cogmyra/`.
- Keep changes minimal and focused on the task at hand.
- Prefer incremental improvements with tests over large rewrites.

## Workflow

- Scaffolding: Add new modules under `src/cogmyra/` and expose public APIs via `__init__.py` as needed.
- Testing: Add or update tests in `tests/` using `pytest`. Ensure `poetry run pytest -q` passes locally.
- Linting/Format: Use Ruff. Fix lints with `ruff check --fix .` and format with `ruff format .`.
- Docs: Update `README.md` when adding notable features or commands. Keep examples runnable.

## Conventions

- Python: 3.11+, type-annotated functions, small focused modules.
- Style: Black-compatible formatting via Ruff; keep line length to 100.
- CI: Ensure CI passes (Ruff checks and pytest). Update CI when adding required services or deps.

## Notes

- Avoid adding new tools unless justified. Favor Poetry groups for dev/test dependencies.
- If a task spans multiple steps, maintain a brief plan and update it as you go.

