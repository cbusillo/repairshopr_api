# AGENTS.md

This repo is managed with uv and publishes to PyPI via GitHub Actions.
Use `.github/github.json` for non-secret repo workflow facts,
validation commands, GitHub signal availability, and docs routing.

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

1. Create a focused release branch from `main`.
2. Bump the version in `pyproject.toml`.
3. Refresh lockfile: `uv lock`.
4. Verify lockfile: `./scripts/check-lockfile.sh`.
5. Open a PR and merge the release branch through GitHub after checks pass.
6. After explicit release approval, update local `main` to the merged commit.
7. Tag the release on `main` (example): `git tag -a vX.Y.Z -m "vX.Y.Z"`.
8. Push the tag only: `git push origin vX.Y.Z`.

Do not commit or push release changes directly to `main`. Agent-authored release
commits and pushes should follow the shared GitHub skill's bot-owned helper
workflow when available.

## Tests

- Install test dependencies: `uv sync --group dev`
- Run test suite: `uv run pytest -q`

## Code Quality

- Run PyCharm inspections on changed files before merge.
- Shared IDE configuration targets PyCharm 2026.2 or newer and the
  `pyproject.toml`-linked module name `repairshopr-api`.
- Keep `.idea/pyLspTools.xml` and `.idea/db-forest-config.xml` local and
  untracked; they contain plugin-specific project state.
- Treat inspections as a hard gate: zero `error`, `warning`, and
  `weak_warning` findings on touched files.
- Do not add suppression comments (`# noinspection`, `# noqa`,
  `# type: ignore`, etc.) unless the maintainer has been notified
  first with rationale and has explicitly approved.
- Follow the inspection gate in [`README.md` - Code Quality Gates](README.md#code-quality-gates).
