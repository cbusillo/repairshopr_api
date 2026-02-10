# TODO: Unstick RepairShopr Sync and Complete Full Pipeline

## Read First

- `AGENTS.md`
- `README.md`
- `scripts/repairshopr-sync-entrypoint.sh`
- `repairshopr_sync/repairshopr_data/management/commands/import_from_repairshopr.py`
- `repairshopr_api/client.py`

## Goal

Get `repairshopr-sync` to finish full cycles reliably (`SYNC_LOOP start` ->
`SYNC_LOOP done`) and then let downstream Odoo imports run against fresh sync DB
data.

## Immediate Ops Steps

1. Verify whether the current cycle is moving:

```bash
cd /Users/cbusillo/Developer/repairshopr_api
set -a
source .env
set +a

uv run python - <<'PY'
import os
import time
import MySQLdb

connection = MySQLdb.connect(
    host=os.environ['SYNC_DB_HOST'],
    port=int(os.getenv('SYNC_DB_PORT', '3307')),
    user=os.environ['SYNC_DB_USER'],
    passwd=os.environ['SYNC_DB_PASSWORD'],
    db=os.environ['SYNC_DB_NAME'],
)
tables = [
    ('repairshopr_data_ticketcomment', 'updated_at'),
    ('repairshopr_data_ticket', 'created_at'),
    ('repairshopr_data_invoice', 'updated_at'),
]
with connection:
    for probe in range(1, 4):
        with connection.cursor() as cursor:
            print(f'probe={probe}')
            for table, column in tables:
                cursor.execute(
                    f"SELECT COUNT(*) total, MAX({column}) max_ts, MAX(id) max_id FROM {table}"
                )
                total, max_ts, max_id = cursor.fetchone()
                print(f'  {table}: total={total} max_ts={max_ts} max_id={max_id}')
        if probe < 3:
            time.sleep(30)
PY
```

1. If rows/timestamps are not changing for 10+ minutes and logs have no
   `SYNC_LOOP done`, restart the `repairshopr-sync` app in Coolify (or via the
   `odoo-ai` ops wrapper) and watch for a fresh `SYNC_LOOP start`.

2. Keep `SYNC_DB_RESET=0` for normal runs. Use `SYNC_DB_RESET=1` only for
   intentional full rebuilds.

## Code Improvements To Implement Next

1. Add model-level progress logs in `import_from_repairshopr`:
   start/done per model with row counts and elapsed seconds.
2. Persist heartbeat/progress markers into a small DB-backed status table (or
   Django cache model) every N pages/records.
3. Add a stale-progress watchdog in the sync loop:
   if no heartbeat updates for a threshold window, fail the cycle explicitly so
   operations sees a clear `Import failed` and can restart automatically.
4. Add a management command for operational status output (single-line JSON):
   current model, page, records processed, last heartbeat, cycle age.

## Validation Criteria

1. Two consecutive cycles complete with explicit `SYNC_LOOP done` log lines.
2. Row counts in high-volume tables increase (or remain stable only when API has
   no new data) while cycle is running.
3. No repeating silent-stall pattern (start line with no done/failed line for an
   extended period).

## Handoff Back To Odoo

After a stable completed cycle, run the Odoo full imports and verify:

1. `repairshopr.last_run_at` is set.
2. `repairshopr.last_run_status=success`.
3. External ID counts in Odoo increase for RepairShopr where expected.
