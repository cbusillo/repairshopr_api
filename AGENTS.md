# AGENTS.md

AGENTS.md is this repository's only agent-instruction file.
This repository has no DIRECTION.md; read the Director's
[overall direction](https://github.com/cbusillo/direction/blob/HEAD/DIRECTION.md)
first and follow its executing loop and stop boundaries through the shared
skills. Keep durable work status in the owning GitHub issue.

For issue-backed work, use `github-plan` to read the issue and linked context,
recheck ownership, and claim before creating a linked task worktree. Use
`github` for bot-owned commits, pushes, and PRs, following the overall direction
for landing. Use
`model-review` for execution-guidance changes such as this file; weigh findings
under the shared review reference. Use `work-closeout` after landing.

This repo is managed with uv and publishes to PyPI via GitHub Actions.
Use `.github/github.json` for non-secret repo workflow facts,
validation commands, GitHub signal availability, and docs routing.

## What RepairShopr API does

RepairShopr API is a Python client for RepairShopr, with models and API helpers.
Its optional Django sync service keeps a local database copy of supported RepairShopr records.
Evidence: [README.md](README.md#sync-coverage).

## Setup

- Python version: `3.14`
- Install dependencies: `uv sync --locked`
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

Follow [README.md — Release (PyPI)](README.md#release-pypi) for the tag-driven
package release procedure.
Agent-authored commits and all pushes, including release tags, use the shared
GitHub skill's `git-commit-as-bot` and `git-push-as-bot` helpers.

Sync image builds and production promotion are separate from package releases;
see [README.md — Sync images and promotion](README.md#sync-images-and-promotion).

## Tests

- Install test dependencies: `uv sync --locked --group dev`
- Follow the [local/CI test command contract](https://github.com/cbusillo/codex-skills/blob/HEAD/skills/github/references/config-schema.md#workflow-metadata).
  Replace `{test_paths}` in `qualityGate.test.local` with a nonempty selection.
  Select whole safety modules for affected flush/recovery commands (`tests/sync`),
  bootstrap/entrypoint/health wrappers (`tests/scripts`), or home-config isolation
  (`tests/test_home_config_isolation.py`); trace callers for other affected modules.
  Focused local runs omit whole-project coverage; CI requires the complete
  `test.ci` coverage gate and the existing MariaDB integration job before ready or merge.

Follow the [shared Tests rule](https://github.com/cbusillo/codex-skills/blob/HEAD/instructions/global.md#tests).

## Code Quality

- Run PyCharm inspections on changed files before opening a PR and before merge.
- Shared IDE configuration targets PyCharm 2026.2 or newer and the
  `pyproject.toml`-linked module name `repairshopr-api`.
- Keep `.idea/pyLspTools.xml` and `.idea/db-forest-config.xml` local and
  untracked; they contain plugin-specific project state.
- Treat inspections as a hard gate: zero `error`, `warning`, and
  `weak_warning` findings on touched files.
- New or changed suppression comments (`# noinspection`, `# noqa`,
  `# type: ignore`, etc.)
  must be narrow: one line or one rule, never a whole file. Include a written
  reason on the same line and name each suppression in the PR body so the
  second-model review sees it.
  For `# noinspection`, use one identifier-style reason token, for example
  `# noinspection PyProtectedMember frameworkRequiresProtectedAccess`, to keep
  the comment compatible with PyCharm's suppression parser.
- Use the `jetbrains-inspection` skill for exact-worktree inspection routing.
