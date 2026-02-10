# repairshopr-api

Python client and sync utilities for RepairShopr.

- `repairshopr_api`: API models and helpers
- `repairshopr_sync`: Django-based sync service (optional)

## Development

- Python version: `3.14`
- Install runtime dependencies: `uv sync`
- Install development dependencies: `uv sync --group dev`
- Build package: `uv build`

## Tests

The repository uses `pytest` with coverage gates.

- Install test dependencies: `uv sync --group dev`
- Run the full suite: `uv run pytest -q`
- Run with explicit coverage output: `uv run pytest --cov --cov-report=term-missing`
- Run MySQL integration tests:

  ```bash
  uv sync --group dev --extra sync
  uv run python -m django migrate --noinput --settings=tests.django_settings_mysql
  uv run pytest -q -m integration --ds=tests.django_settings_mysql --no-cov
  ```

Notes:

- Tests do not call the live RepairShopr API.
- Shell tests for `scripts/repairshopr-sync-entrypoint.sh` run with command stubs.
- The default coverage threshold is enforced at `80%`.
- A dedicated CI job runs MySQL-backed integration checks for schema/migrations.

## Release (PyPI)

Releases are tag-driven. The GitHub Actions workflow publishes to PyPI only
when a tag matching `v*` is pushed.

1. Bump the version in `pyproject.toml`.
2. Commit the changes on `main`.
3. Create a tag `vX.Y.Z` at that commit.
4. Push the commit and tag: `git push origin main --follow-tags`.

Pushing to `main` without a tag does not publish.
