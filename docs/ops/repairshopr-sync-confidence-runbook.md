# RepairShopr Sync Confidence Runbook

This runbook defines a repeatable, single-writer workflow for forensic scanning,
targeted repair, and confidence gating of invoice line-item sync.

## Why This Exists

The global `line_items` feed can report unstable page slices on a moving dataset.
`meta.total_entries` is useful telemetry, but it is not a strict correctness source
for unique row parity.

Use forensic metrics from `reconcile_invoice_line_items` as the primary truth for
drift analysis and repair decisions.

## Single-Writer Rule

Never run these at the same time:

- continuous `sync` service
- one-off `reconcile_invoice_line_items --apply`

Always stop `sync` first, run reconcile, then restart `sync`.

## Prerequisites

- Deploy image built from current `main`.
- `sync` and `db` services managed by Compose.
- `reconcile_invoice_line_items` command available.

## Phase 1: Forensic-Only Scan

1. Stop `sync` service.
2. Run forensic scan without writes.

```bash
docker compose -p <project_name> \
  -f docker/coolify/repairshopr-sync.yml \
  --env-file .env \
  stop sync

docker compose -p <project_name> \
  -f docker/coolify/repairshopr-sync.yml \
  --env-file .env \
  run --rm sync \
  python /app/repairshopr_sync/manage.py reconcile_invoice_line_items \
  --compute-db-not-in-api
```

1. Save JSON outputs (`scan_progress`, `forensic_summary`) for the run record.

## Phase 2: Targeted Apply Pass

1. Keep `sync` stopped.
2. Run reconcile with apply.

```bash
docker compose -p <project_name> \
  -f docker/coolify/repairshopr-sync.yml \
  --env-file .env \
  run --rm sync \
  python /app/repairshopr_sync/manage.py reconcile_invoice_line_items \
  --apply --compute-db-not-in-api
```

1. Save JSON outputs (`repair_progress`, `repair_summary`, `forensic_summary`).

## Phase 3: Resume Incremental Sync

1. Set `last_updated_at` to current UTC to avoid forced full-cycle reruns.
2. Start `sync` service.

```bash
# example edit in config: last_updated_at = 2026-02-16T19:00:00Z
docker compose -p <project_name> \
  -f docker/coolify/repairshopr-sync.yml \
  --env-file .env \
  up -d sync
```

## Confidence Gates

For each run, record `forensic_summary` and compare to prior runs.

- `api_duplicate_rows`: expected non-zero on unstable global feed.
- `api_unique_not_in_db`: should be stable or decreasing after apply runs.
- `missing_invoice_ids_without_parent_invoice_row`: should remain low.
  Investigate spikes.
- `db_null_parent_invoice_id_count`: should stay stable or improve.

If any metric worsens significantly across two consecutive runs, switch to
forensic-only mode and investigate before additional apply runs.

## Rebuild / Recreate Flow

For database delete/recreate scenarios:

1. Recreate DB and run migrations.
2. Run initial sync bootstrap.
3. Stop `sync` and run forensic-only pass.
4. Run targeted apply pass.
5. Resume `sync` incremental mode.
6. Run another forensic pass to verify post-rebuild stability.

## What Is Intentionally Not Used As A Hard Gate

- `line_item meta.total_entries` global parity vs DB row count

Use it as telemetry only; base decisions on forensic unique-ID metrics.
