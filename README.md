# repairshopr-api

Python client and sync utilities for RepairShopr.

- `repairshopr_api`: API models and helpers
- `repairshopr_sync`: Django-based sync service (optional)

## Project direction

The Director's [overall direction](https://github.com/cbusillo/direction/blob/HEAD/DIRECTION.md)
applies; this repository has no DIRECTION.md of its own.
[AGENTS.md](AGENTS.md) is the only agent-instruction file and owns the
repository's agent workflow and quality requirements. Workflow facts and
validation commands are recorded in [.github/github.json](.github/github.json).

## Development

- Python version: `3.14`
- Install project dependencies (including the default `dev` group): `uv sync --locked`
- Install runtime dependencies only: `uv sync --locked --no-dev`
- Install development dependencies explicitly: `uv sync --locked --group dev`
- Build package: `uv build`

### Display client settings

Run `uv run python -m repairshopr_api.config.display_settings` from the project
root, or use PyCharm's **Display Client Settings** run configuration. The command
prints the Repairshopr and Django settings as JSON, including defaults. Credential
values and additional fields outside the known public settings are shown as
`[REDACTED]`; the existing `display_settings()` callable still returns raw fields.
The command uses the normal settings initializer, which can create or rewrite the
configured TOML file and prompt for values marked `from_terminal`.

## Lockfile Guardrails

This repo treats `uv.lock` as a committed artifact and enforces lockfile
consistency with local checks and CI.

- Check lockfile consistency: `./scripts/check-lockfile.sh`
- Refresh lockfile after dependency/version changes: `uv lock`
- Ensure both files are committed together when needed:
  `git add pyproject.toml uv.lock`

## Tests

The repository uses `pytest` with coverage gates.

- Install test dependencies: `uv sync --locked --group dev`
- Run the full suite: `uv run pytest -q`
- Run with explicit coverage output: `uv run pytest --cov --cov-report=term-missing`
- Run MariaDB integration tests against a local database initialized with the
  CI defaults:

  ```bash
  uv sync --locked --group dev --extra sync
  export RUN_MARIADB_INTEGRATION=1
  export MARIADB_DATABASE=repairshopr_test
  export MARIADB_USER=repairshopr_api
  export MARIADB_PASSWORD=root
  uv run python -m django migrate --noinput \
    --settings=tests.django_settings_mariadb
  uv run python -m django makemigrations --check --dry-run \
    --settings=tests.django_settings_mariadb
  uv run pytest -q -m integration \
    --ds=tests.django_settings_mariadb --no-cov
  ```

Notes:

- Tests do not call the live RepairShopr API.
- Shell tests for `scripts/repairshopr-sync-entrypoint.sh` run with command stubs.
- The default coverage threshold is enforced at `80%`.
- A dedicated CI job runs MariaDB-backed integration checks for
  schema/migrations using the database image declared by the production Compose
  contract.
- Dependabot opens Django-stack updates separately from other Python dependency
  updates and monitors the production Compose database image directly.

## Line Item Forensics

Use the dedicated reconcile command to diagnose invoice line-item drift without
waiting for a full sync cycle.

`reconcile_invoice_line_items` is forensic-only. The older repair flags
`--apply` and `--max-repair-invoices` are no longer supported.

See the production runbook in
`docs/ops/repairshopr-sync-confidence-runbook.md`.

- Forensic scan only:

  ```bash
  uv run python repairshopr_sync/manage.py reconcile_invoice_line_items
  ```

- Optional deep metric (`db_not_in_api_unique`):

  ```bash
  uv run python repairshopr_sync/manage.py reconcile_invoice_line_items \
    --compute-db-not-in-api
  ```

## Code Quality Gates

Changed code is inspected in PyCharm before a PR and merge, alongside the
pytest/coverage gates above. See [AGENTS.md — Code Quality](AGENTS.md#code-quality)
for thresholds, suppression approval, and worktree-safe inspection routing.

## Release (PyPI)

Releases are tag-driven. The GitHub Actions workflow publishes to PyPI only
when a tag matching `v*` is pushed.

1. Create a focused release branch from `main`.
2. Bump the version in `pyproject.toml`.
3. Refresh lockfile: `uv lock`.
4. Confirm lockfile is clean: `./scripts/check-lockfile.sh`.
5. Open a PR and merge the release branch through GitHub after checks pass.
6. After explicit release approval, update local `main` to the merged commit.
7. Create a tag `vX.Y.Z` at that commit.
8. Push the tag only. For agent work, use the shared GitHub skill's
   `git-push-as-bot origin vX.Y.Z` helper.

Do not commit or push release changes directly to `main`.

Pushing to `main` without a tag does not publish to PyPI.

## Sync images and promotion

RepairShopr Sync runs as the `sync` container in
[`addons/repairshopr-sync/compose.yml`](addons/repairshopr-sync/compose.yml).

A merge to `main` runs the `Build` workflow: tests pass before it publishes a
commit-addressed sync image to GHCR and uploads an artifact manifest.
Launchplane consumes that completed push run for the testing lane; this
repository does not call Launchplane directly. Production promotion follows
the [overall direction](https://github.com/cbusillo/direction/blob/HEAD/DIRECTION.md)
and the [sync operations runbook](docs/ops/repairshopr-sync-confidence-runbook.md).
The remaining release-routing work is tracked in
[#103](https://github.com/cbusillo/repairshopr_api/issues/103).
