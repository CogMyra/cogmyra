![CI](https://github.com/CogMyra/cogmyra/actions/workflows/ci.yml/badge.svg)

# CogMyra

AI-powered personalized learning platform.

## Vision

- Empower learners with adaptive, AI-driven experiences.
- Deliver meaningful insights for instructors and organizations.
- Build an open, developer-friendly platform.

## Mission

- Provide personalized learning paths and timely feedback.
- Make high-quality learning accessible and engaging for everyone.
- Enable rapid iteration via strong tooling, tests, and docs.

## Quick Start

Prerequisites: Python 3.11+ and Poetry installed.

```
poetry install
poetry run pytest -q
```

## Roadmap

- [ ] MVP features and data model
- [ ] Integrations and content ingestion
- [ ] Analytics and progress insights
- [ ] UI/UX and accessibility

## CLI

Install deps and run:

```bash
poetry install
poetry run cogmyra greet World
poetry run cogmyra mem add "example note" --user u1 --file mem.jsonl
poetry run cogmyra mem last --n 5 --file mem.jsonl
poetry run cogmyra mem search example --file mem.jsonl
git tag -a v0.2.0 -m "v0.2.0: add Typer CLI (greet + mem)"
git push origin v0.2.0
gh release create v0.2.0 --generate-notes
poetry build
poetry publish -r testpypi
python3 -m venv /tmp/cogvenv && source /tmp/cogvenv/bin/activate
python -m pip install --upgrade pip
python -m pip install -i https://test.pypi.org/simple cogmyra
cogmyra greet World


```
