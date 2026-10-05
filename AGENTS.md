# AGENTS.md

AGENTS.md is this repository's only agent-instruction file.
This repository has no DIRECTION.md; read the Director's
[overall direction](https://github.com/cbusillo/direction/blob/HEAD/DIRECTION.md)
first and follow its executing loop and stop boundaries through the shared
skills. Keep durable work status in the owning GitHub issue.

For issue-backed work, use `github-plan` to read the issue and linked context,
recheck ownership, and claim before creating a linked task worktree. Use
`github` for bot-owned commits, pushes, and PRs. This repository does not use
the Launchplane merge train: when merge authority covers the change, land a
normal merge commit after green CI and the applicable quality gates. Use
`model-review` for execution-guidance changes such as this file; weigh findings
under the shared review reference. Use `work-closeout` after landing.

This repo is managed with uv and publishes to PyPI via GitHub Actions.
Use `.github/github.json` for non-secret repo workflow facts,
validation commands, GitHub signal availability, and docs routing.

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
package release procedure. A source merge does not authorize a release.
Agent-authored commits and all pushes, including release tags, use the shared
GitHub skill's `git-commit-as-bot` and `git-push-as-bot` helpers.

Sync image builds and production promotion are separate from package releases;
see [README.md — Sync images and promotion](README.md#sync-images-and-promotion).

## Tests

- Install test dependencies: `uv sync --locked --group dev`
- Run test suite: `uv run pytest -q`
- A test must fail when the product is broken and pass when someone makes an
  intended change. Do not assert a literal defined elsewhere (versions, build
  numbers, toolchain, pinned SHAs, hashes); check agreement with one source of
  truth or leave it out.
- Do not assert workflow, compose, dependabot, or IDE config text. Enforce
  those rules where they execute (the workflow itself, a helper script with its
  own unit test, or `actionlint`).
- Verification and loading code must not depend on working-tree state (for
  example `git ls-files` or local IDE files); check live state only on the
  path that acts on it.

## Code Quality

- Run PyCharm inspections on changed files before opening a PR and before merge.
- Shared IDE configuration targets PyCharm 2026.2 or newer and the
  `pyproject.toml`-linked module name `repairshopr-api`.
- Keep `.idea/pyLspTools.xml` and `.idea/db-forest-config.xml` local and
  untracked; they contain plugin-specific project state.
- Treat inspections as a hard gate: zero `error`, `warning`, and
  `weak_warning` findings on touched files.
- Do not add suppression comments (`# noinspection`, `# noqa`,
  `# type: ignore`, etc.) unless the maintainer has been notified
  first with rationale and has explicitly approved.
- Use the `jetbrains-inspection` skill for exact-worktree inspection routing.
