# repairshopr-api

Python client and sync utilities for RepairShopr.

- `repairshopr_api`: API models and helpers
- `repairshopr_sync`: Django-based sync service (optional)

## Development

- Python version: `3.14`
- Install runtime dependencies: `uv sync`
- Install development dependencies: `uv sync --group dev`
- Build package: `uv build`

## Lockfile Guardrails

This repo treats `uv.lock` as a committed artifact and enforces lockfile
consistency with local checks and CI.

- Check lockfile consistency: `./scripts/check-lockfile.sh`
- Refresh lockfile after dependency/version changes: `uv lock`
- Ensure both files are committed together when needed:
  `git add pyproject.toml uv.lock`

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

## Code Quality Gates

In addition to tests, run IDE inspections on changed code before opening a PR.

- PyCharm: run **Inspect Code** on changed files (or whole project for larger changes).
- Required threshold: zero `error`, `warning`, and `weak_warning`
  findings in touched files.
- Do not add suppressions (`# noinspection`, `# noqa`,
  `# type: ignore`, etc.) without explicit maintainer approval.
- If a suppression seems necessary, stop and document the exact
  rule, why it is unavoidable/false-positive, and the narrowest
  possible suppression for approval first.

This is a local quality gate and complements (does not replace) the pytest/coverage
gates above.

## Release (PyPI)

Releases are tag-driven. The GitHub Actions workflow publishes to PyPI only
when a tag matching `v*` is pushed.

1. Bump the version in `pyproject.toml`.
2. Refresh lockfile: `uv lock`.
3. Confirm lockfile is clean: `./scripts/check-lockfile.sh`.
4. Commit the changes on `main`.
5. Create a tag `vX.Y.Z` at that commit.
6. Push the commit and tag: `git push origin main --follow-tags`.

Pushing to `main` without a tag does not publish.
