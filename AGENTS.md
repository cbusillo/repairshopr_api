# AGENTS.md

This repo is managed with uv and publishes to PyPI via GitHub Actions.

## Setup

- Python version: `3.14`
- Install dependencies: `uv sync`
- Build package: `uv build`

## Lockfile policy

- `uv.lock` must stay in sync with `pyproject.toml`.
- Check consistency with: `./scripts/check-lockfile.sh`
- If dependency metadata changes, run: `uv lock`
- Commit `pyproject.toml` and `uv.lock` together when version/dependency data
  changes.
- CI intentionally uses locked installs (`uv sync --locked ...`) and will fail on
  lockfile drift.

## Release

The `Publish to PyPI` workflow is tag-driven and runs only on tags matching
`v*`.

1. Bump the version in `pyproject.toml`.
2. Refresh lockfile: `uv lock`.
3. Verify lockfile: `./scripts/check-lockfile.sh`.
4. Commit the changes on `main`.
5. Tag the release (example): `git tag -a vX.Y.Z -m "vX.Y.Z"`.
6. Push commit and tag: `git push origin main --follow-tags`.

## Tests

- Install test dependencies: `uv sync --group dev`
- Run test suite: `uv run pytest -q`

## Code Quality

- Run PyCharm inspections on changed files before merge.
- Follow the inspection gate in [`README.md` - Code Quality Gates](README.md#code-quality-gates).
