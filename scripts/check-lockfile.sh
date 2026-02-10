#!/usr/bin/env bash

set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
	echo "ERROR: uv is required to validate uv.lock." >&2
	exit 1
fi

if uv lock --check; then
	exit 0
fi

cat >&2 <<'EOF'

Dependency lockfile drift detected.

`uv.lock` is not in sync with `pyproject.toml`.

Fix it locally:
  1. uv lock
  2. git add pyproject.toml uv.lock
  3. Commit again

CI uses `uv sync --locked`, so stale lockfiles fail fast by design.
EOF

exit 1
