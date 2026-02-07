# AGENTS.md

This repo is managed with Poetry and publishes to PyPI via GitHub Actions.

## Setup

- Install dependencies: `poetry install`
- Build package: `poetry build`

## Release

The `Publish to PyPI` workflow is tag-driven and runs only on tags matching
`v*`.

1. Bump the version in `pyproject.toml`.
2. Commit the changes on `main`.
3. Tag the release (example): `git tag -a vX.Y.Z -m "vX.Y.Z"`.
4. Push commit and tag: `git push origin main --follow-tags`.

## Tests

No automated test runner is configured in this repo. Ask before adding or
changing test tooling.
