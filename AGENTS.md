# AGENTS.md

This repo is managed with uv and publishes to PyPI via GitHub Actions.

## Setup

- Python version: `3.14`
- Install dependencies: `uv sync`
- Build package: `uv build`

## Release

The `Publish to PyPI` workflow is tag-driven and runs only on tags matching
`v*`.

1. Bump the version in `pyproject.toml`.
2. Commit the changes on `main`.
3. Tag the release (example): `git tag -a vX.Y.Z -m "vX.Y.Z"`.
4. Push commit and tag: `git push origin main --follow-tags`.

## Tests

- Install test dependencies: `uv sync --group dev`
- Run test suite: `uv run pytest -q`
