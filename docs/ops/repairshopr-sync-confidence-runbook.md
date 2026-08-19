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

Deploys are requested through Launchplane. This repository publishes an
immutable sync image for the tested commit and submits the image digest to
Launchplane; it must not store Dokploy host, token, compose id, or provider
mutation logic in workflow code.

The GitHub workflow builds and publishes the tested image, then calls
Launchplane's reusable generic-web stable deploy workflow with only the product
key, lane instance, immutable image digest, and tested source SHA. Launchplane
owns the route payload, idempotency key policy, provider target resolution,
provider mutation, deployment polling, and deployment evidence.

When an existing deploy reservation requires inspection, use the manual
`Launchplane Deploy` workflow's manual dispatch path. It accepts the exact
original product, instance, immutable artifact, source commit, GitHub Actions
run ID and attempt, and an operator reason. It reconstructs the exact legacy
deploy idempotency key through Launchplane's bounded recovery action, then calls
only the read-only existing-reservation recovery route through GitHub Actions
OIDC under the same authorized `workflow_run` and reusable workflow identities as
stable deploy. Operators dispatch `Launchplane Recovery Request`, which only
stages a one-day request artifact. `Launchplane Deploy` accepts that artifact
only from a successful manual run on `main` and invokes the reusable
recovery-only job. The reusable Launchplane workflow validates the exact source
workflow and consumes the triggering run's bounded artifact centrally. The
bridge cannot build, publish, or deploy an image, and it exposes no recovery
apply mode. Review the bounded recovery digest, proposed action, reservation
state, and provider classification in the `Launchplane Deploy` workflow summary.

After separate explicit approval, dispatch `Launchplane Recovery Apply Request`
with the identical original deploy coordinates and the exact reviewed recovery
digest. The staging workflow has no OIDC permission and only uploads a one-day
bounded artifact. `Launchplane Deploy` accepts that artifact only from a
successful manual run on `main`, verifies its single-file schema, size, target,
immutable image, source commit, original run identity, reason, and digest, then
calls the digest-gated recovery apply route under the existing authorized
`workflow_run` identity. The Launchplane service performs a fresh inspection
and rejects stale evidence before writing. The workflow suppresses the raw
response and succeeds only when the result proves `adopt_observed`, completed
reservation state, present/done provider evidence, the exact reviewed digest,
and `retry_safe=false`. It never exposes or enables provider retry.

The MariaDB integration gate resolves its database image from
`addons/repairshopr-sync/compose.yml` and starts an isolated container from that
image. Database image updates therefore exercise migrations and schema checks in
CI before the same Compose contract is deployed.

## Launchplane Health Readiness

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
status, a failed last cycle, stale heartbeat, unavailable sync database status,
or malformed `LAUNCHPLANE_RUNTIME_IDENTITY_JSON` returns HTTP 503 with
`status: "not_ready"` and `not_ready_reasons`.

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
