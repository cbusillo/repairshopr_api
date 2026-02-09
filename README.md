# repairshopr-api

Python client and sync utilities for RepairShopr.

- `repairshopr_api`: API models and helpers
- `repairshopr_sync`: Django-based sync service (optional)

## Development

- Install dependencies: `poetry install`
- Build package: `poetry build`

## Tests

The repository uses `pytest` with coverage gates.

- Install test dependencies: `poetry install --with dev`
- Run the full suite: `poetry run pytest -q`
- Run with explicit coverage output: `poetry run pytest --cov --cov-report=term-missing`

Notes:

- Tests do not call the live RepairShopr API.
- Shell tests for `scripts/repairshopr-sync-entrypoint.sh` run with command stubs.
- The default coverage threshold is enforced at `80%`.

## Release (PyPI)

Releases are tag-driven. The GitHub Actions workflow publishes to PyPI only
when a tag matching `v*` is pushed.

1. Bump the version in `pyproject.toml`.
2. Commit the changes on `main`.
3. Create a tag `vX.Y.Z` at that commit.
4. Push the commit and tag: `git push origin main --follow-tags`.

Pushing to `main` without a tag does not publish.
