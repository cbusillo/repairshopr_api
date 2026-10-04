# RepairShopr Sync Confidence Runbook

This runbook defines a repeatable, single-writer workflow for forensic scanning
and confidence gating of invoice line-item sync.

## Why This Exists

The global `line_items` feed can report unstable page slices on a moving dataset.
`meta.total_entries` is useful telemetry, but it is not a strict correctness source
for unique row parity.

Use forensic metrics from `reconcile_invoice_line_items` as the primary truth for
drift analysis.

## Single-Writer Rule

Never run these at the same time:

- continuous `sync` service
- one-off `reconcile_invoice_line_items`

Always stop `sync` first, run reconcile, then restart `sync`.

## Prerequisites

- Deploy image built from current `main`.
- `sync` and `db` services managed by Compose.
- `reconcile_invoice_line_items` command available.

## Deployment Boundary

Launchplane owns every deploy. This repository builds and publishes an
immutable sync image for each tested commit; it must not store Dokploy host,
token, compose id, or provider mutation logic in workflow code.

A merge to `main` never changes production. The `Build` workflow runs on the
push to `main`: it runs the `Test Suite`, builds and publishes the image as
`ghcr.io/cbusillo/repairshopr_api:sha-<commit>`, and uploads one
`artifact-manifest-<run attempt>` artifact naming the commit and the image's
immutable digest. Launchplane reacts to that completed run: it verifies the run
and the manifest, and deploys the image to the product's `testing` lane. No
workflow here calls Launchplane or holds a Launchplane grant.

The artifact production runs changes only through a Launchplane promotion from
the product's `testing` lane, requested in Launchplane rather than from this
repository. Launchplane requires the accepted release, captures and verifies a
production backup, deploys the artifact the testing lane runs, checks health,
writes the promotion record, and rolls production back on its own if the deploy
or health check fails. A release needs acceptance as the product record shows
it: the product's Client accepts it in Launchplane, or, when the Client is the
Director, the Director's standing direction is the acceptance. Launchplane
refuses a direct deploy that would change the artifact production runs
(`promotion_required`). Deploy recovery is an admin action in Launchplane.

A testing lane on the production Docker host must set its own
`SYNC_DB_VOLUME_NAME`, `SYNC_CONFIG_VOLUME_NAME`, `SYNC_DB_HOST_PORT` and
`SYNC_HEALTH_HOST_PORT`; the defaults are production's. The `Test Suite`
renders the compose contract both ways and fails if a second lane would share
a volume or host port. A testing lane holds its own database and never
production's sync-database or RepairShopr credentials.

The MariaDB integration gate resolves its database image from
`addons/repairshopr-sync/compose.yml` and starts an isolated container from that
image. Database image updates therefore exercise migrations and schema checks in
CI before the same Compose contract is deployed.

## Launchplane Health Readiness

At startup, the sync entrypoint runs the optional database flush
(`SYNC_DB_RESET=1`) and then migrations before importing. If either command
fails, it waits `SYNC_FAILURE_SLEEP_SECONDS` (default 60 seconds) and exits
nonzero so the container restart policy can retry startup. It never enters the
sync loop after a failed flush or migration.
These overrides apply when set directly in the container environment; the
add-on Compose contract does not forward either setting. With `SYNC_DB_RESET=1`,
the flush repeats on every container restart, including migration retries.

The `sync` container serves JSON readiness while the background sync loop is
running. `docker/coolify/compose.yml` remains the provider entrypoint and loads
the product-owned add-on contract from `addons/repairshopr-sync/compose.yml`.
The `sync` service image comes from Launchplane/provider env key
`DOCKER_IMAGE_REFERENCE`, which is set to the immutable digest selected for the
deploy.

- Path: `/readyz` or `/health`
- Default bind: `0.0.0.0:8000`
- Compose exposure: `SYNC_HEALTH_HOST_PORT` publishes to `SYNC_HEALTH_PORT`,
  both defaulting to `8000`
- Freshness threshold: `SYNC_HEALTH_STALE_THRESHOLD_SECONDS`, falling back to
  `SYNC_STALE_HEARTBEAT_SECONDS`, then 900 seconds

Readiness returns HTTP 503 with `startup_incomplete` until this container's
startup flush (when enabled) and migrations succeed, even if the database still
holds a recent successful sync from a previous process. The default container
wrapper creates a private temporary startup marker path, shares it with the
health server and sync entrypoint, and removes it on normal exit. Abrupt process
death can leave the directory behind, but each wrapper run uses a new path; `SYNC_STARTUP_COMPLETE_FILE` is internal process state and must not
be set in lane configuration or stored on a persistent volume. The entrypoint
writes the marker only after successful migrations. A standalone health server
without the wrapper's startup signal stays non-ready; run
`python scripts/repairshopr_sync_with_health.py` to start both processes together.
Startup completion only makes readiness eligible: existing sync freshness,
failure, database and runtime-identity checks still apply.

Launchplane should route generic-web health checks to the readiness path for the
product lane after deploy. The repo exposes the port and endpoint shape only;
Launchplane operator records own live product URLs, provider IDs, and
lane-specific routing.

The compose contract forwards Launchplane's runtime identity variables into the
sync container. The payload includes package version, the deployed
`DOCKER_IMAGE_REFERENCE`, parsed `LAUNCHPLANE_RUNTIME_IDENTITY_JSON` under
`runtime_identity`, and the same `SyncStatus` freshness data used by the
`sync_status` watchdog command. Fallback runtime fields come from
`LAUNCHPLANE_DEPLOYMENT_RECORD_ID`, `LAUNCHPLANE_ARTIFACT_ID`, and
`LAUNCHPLANE_SOURCE_GIT_REF` when the structured runtime identity env var is not
present.

Readiness returns HTTP 200 only when the sync state is acceptable. Missing sync
status, a failed last cycle, stale heartbeat, an overdue next cycle, unavailable
sync database status, or malformed `LAUNCHPLANE_RUNTIME_IDENTITY_JSON` returns
HTTP 503 with `status: "not_ready"` and `not_ready_reasons`. The next cycle is
overdue (`sync_overdue`) when the last cycle succeeded but finished more than
`SYNC_INTERVAL_SECONDS` plus the freshness threshold ago, so a loop that stops
starting new cycles is reported even though its last cycle was clean.

After deploy, Launchplane can verify the provider route from its host network by
requesting the lane health URL and confirming the response contains
`service: "repairshopr-sync"`, `version`, top-level `status`, `sync`, and
`runtime_identity` when Launchplane injects it.

## Phase 1: Forensic-Only Scan

1. Stop `sync` service.
2. Run forensic scan without writes.

```bash
docker compose -p <project_name> \
  -f docker/coolify/compose.yml \
  --env-file .env \
  stop sync

docker compose -p <project_name> \
  -f docker/coolify/compose.yml \
  --env-file .env \
  run --rm sync \
  python /app/repairshopr_sync/manage.py reconcile_invoice_line_items \
  --compute-db-not-in-api
```

1. Save JSON outputs (`scan_progress`, `forensic_summary`) for the run record.

## Phase 2: Resume Incremental Sync

1. Keep the existing `last_updated_at` watermark by default.
2. Start `sync` service.

Only set `last_updated_at` to current UTC if you explicitly want to skip
changes that may have happened while `sync` was stopped.

```bash
docker compose -p <project_name> \
  -f docker/coolify/compose.yml \
  --env-file .env \
  up -d sync
```

## Confidence Gates

For each run, record `forensic_summary` and compare to prior runs.

- `api_duplicate_rows`: expected non-zero on unstable global feed.
- `api_unique_not_in_db`: should be stable over time; investigate sustained growth.
- `missing_invoice_ids_without_parent_invoice_row`: should remain low.
  Investigate spikes.
- `db_null_parent_invoice_id_count`: should stay stable or improve.

If any metric worsens significantly across two consecutive runs, switch to
forensic-only diagnosis and investigate before restarting normal sync cadence.

## Rebuild / Recreate Flow

For database delete/recreate scenarios:

1. Recreate DB and run migrations.
2. Run initial sync bootstrap.
3. Stop `sync` and run forensic-only pass.
4. Resume `sync` incremental mode.
5. Run another forensic pass to verify post-rebuild stability.

## What Is Intentionally Not Used As A Hard Gate

- `line_item meta.total_entries` global parity vs DB row count

Use it as telemetry only; base decisions on forensic unique-ID metrics.
