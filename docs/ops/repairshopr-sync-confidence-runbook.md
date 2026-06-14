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

Deploys are requested through Launchplane. This repository publishes the tested
commit ref to Launchplane and must not store Dokploy host, token, compose id, or
provider mutation logic in workflow code.

The GitHub workflow uses GitHub OIDC and public-safe Launchplane routing
variables to call the Launchplane deploy route. Launchplane owns provider target
resolution, provider mutation, deployment polling, and source-ref restore.

## Launchplane Health Readiness

The `sync` container serves JSON readiness while the background sync loop is
running:

- Path: `/readyz` or `/health`
- Default bind: `0.0.0.0:8000`
- Freshness threshold: `SYNC_HEALTH_STALE_THRESHOLD_SECONDS`, falling back to
  `SYNC_STALE_HEARTBEAT_SECONDS`, then 900 seconds

Launchplane should route generic-web health checks to the readiness path for the
product lane. The repo exposes the port and endpoint shape only; Launchplane
operator records own live product URLs, provider IDs, and lane-specific routing.

The payload includes package version, source/image hints when the runtime
provides them, parsed `LAUNCHPLANE_RUNTIME_IDENTITY_JSON` under
`runtime_identity`, and the same `SyncStatus` freshness data used by the
`sync_status` watchdog command. Fallback runtime fields come from
`LAUNCHPLANE_DEPLOYMENT_RECORD_ID`, `LAUNCHPLANE_ARTIFACT_ID`, and
`LAUNCHPLANE_SOURCE_GIT_REF` when the structured runtime identity env var is not
present.

Readiness returns HTTP 200 only when the sync state is acceptable. Missing sync
status, a failed last cycle, stale heartbeat, unavailable sync database status,
or malformed `LAUNCHPLANE_RUNTIME_IDENTITY_JSON` returns HTTP 503 with
`status: "not_ready"` and `not_ready_reasons`.

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
