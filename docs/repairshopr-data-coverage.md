# RepairShopr data coverage, October 12, 2026

This is the measured source comparison for [#126](https://github.com/cbusillo/repairshopr_api/issues/126), including [#92](https://github.com/cbusillo/repairshopr_api/issues/92). It compares our live sync database with the `repairshopr` schema on CM's cm_data server. No source data was changed, and no Justin code was read or copied. Both accounts were verified SELECT-only with TLS and consistent READ ONLY snapshots. Snapshots began about 11:06–11:09 PM ET; servers were read separately, not atomically. October is partial. Counts and ID overlap establish differences between copies, not that either copy is a complete vendor reference.

The aggregate evidence files contain no record IDs, customer details or credentials:

- [Table coverage](coverage/2026-10-12/table-coverage.csv): all 58 cm_data tables plus unmatched sync tables, exact counts, matching sync tables and ID overlap where compared.
- [Field coverage](coverage/2026-10-12/field-coverage.csv): all 962 cm_data columns, types, non-null counts and corresponding sync fields, followed by sync-only fields. Population is not proof of equal values or equal meaning.
- [Monthly coverage](coverage/2026-10-12/monthly-coverage.csv): all eleven matched source collections by creation month and ID difference. Our UTC timestamps are converted to Eastern; CM's timestamps are treated as Eastern, consistent with the independently observed offsets in [the earlier correlation](https://github.com/cbusillo/odoo-tenant-cm/issues/167#issuecomment-6136854587). Unknown dates have their own bucket. This convention is not a cross-server timestamp guarantee.

## Measured gaps

| Collection | Our rows | cm_data rows | Shared IDs | cm_data IDs absent here | Our IDs absent there |
| --- | ---: | ---: | ---: | ---: | ---: |
| Customers | 155 | 155 | 155 | 0 | 0 |
| Contacts | 270 | 267 | 261 | 6 | 9 |
| Estimates | 25,217 | 25,217 | 25,217 | 0 | 0 |
| Estimate lines | 139,488 | 138,962 | 138,347 | 615 | 1,141 |
| Invoices | 176,910 | 164,570 | 164,570 | 0 | 12,340 |
| Invoice lines | 613,162 | 649,724 | 612,668 | **37,056** | 494 |
| Payments | 13,471 | 13,464 | 13,464 | 0 | 7 |
| Products | 2,371 | 2,371 | 2,371 | 0 | 0 |
| Tickets | 179,831 | 179,832 | 179,830 | 2 | 1 |
| Comments | 167,335 | 1,652,520 | 167,248 | **1,485,272** | 87 |
| Users | 50 | 86 | 50 | 36 | 0 |

The **36,562 net invoice-line difference** hides 37,056 absent IDs and 494 retained or differently collected IDs. All 19,016 affected invoices exist locally and already have some lines. Shared invoice-line, estimate-line and comment parent IDs agree. Our invoice lines include 388 rows with null parents; comments include 86 with null tickets. Those are separate relation gaps, not additional absent IDs.

The line gap is predominantly historical: 36,726 absent lines were created June 2022–June 2024; only 330 afterward, through February 2026. Four deterministic early affected invoices were checked against the live parent-filtered API. All **seven absent IDs in that sample** were returned. This proves those seven remain recoverable and are not deleted upstream. It does not establish the current availability of every missing line or the exact original incident.

The code provides a concrete failure mechanism: full sync used the bulk line-item feed to construct per-invoice cached pages. Any invoice with *some* prefetched lines was treated as complete, and synthetic metadata described only those rows. Later incremental cycles revisit only changed invoices, so an unchanged partially imported parent never catches up. A moving bulk feed, duplicate pages or historical vendor under-delivery can trigger this mechanism. The original bulk responses are unavailable; their particular failure is not proved. A regression test reproduces partial bulk delivery and verifies that the importer now reads the complete parent feed.

For comments, the [official specification](https://api-docs.repairshopr.com/swagger.json) describes the March 31, 2026 first-comment transition. The old importer trusted embedded comments; [#127](https://github.com/cbusillo/repairshopr_api/pull/127) fixes subsequent selected-ticket imports but has not been qualified in production. Missing IDs span the entire history, including old comments on unchanged tickets. A bounded live per-ticket GET returned a selected missing recent comment and seven other comments on its ticket. This confirms recoverability for that sample; the whole 1.49 million gap is not attributed solely to a dated vendor change.

Nobody was alerted by correctness status because aggregate gaps and even sample failures/mismatches only logged warnings, then advanced the checkpoint and marked the cycle successful. Full-sync sampling could read the same incomplete prefetch cache used by the importer. Comparing only row counts also misses swapped IDs and duplicates. The patch samples fresh unique IDs, tolerates retained local-only IDs, and fails the cycle without advancing its checkpoint when a sampled API ID is missing or the sample cannot be verified. Aggregate vendor totals remain telemetry, because they are not strict unique-ID truth. Samples are bounded; passing one does not prove full coverage.

## Fields and source relationships

All 2,371 product IDs have identical notes and UPC hashes between the two copies; both have **1,746 `[FB:part]` tags**. Our sync already preserves these notes. These are a part-mapping signal, not proof of physical consumption. No new derived Fishbowl mapping is needed in this sync.

cm_data has **642,013 `employee_output` rows**, with repair/diagnostic/QC/intake/invoice counters, employee and ticket references, comment/invoice links, validity and rework fields. Of 601,634 rows carrying a comment ID, 584,283 join to a current comment; 584,272 of those have the same timestamp. There are 131,647 rows with `repairs > 0`. This supports comment-event timing as a source relationship, but does not prove the parser, meaning of counts, correction rules or original timezone. It is **not an official RepairShopr endpoint**.

The **10,504 `part_comments`** rows include parts arrays and note/ticket/comment/employee references. Of them, 10,383 join a current comment and all those timestamps agree. They are annotations whose consumption meaning is unverified. The **238,004 ticket-status-history** rows, output-comment revisions, product corrections, deleted-row tables, WAG claims and outboxes also have no direct counterpart in our API mirror. Several are backups, processing state or custom business logic; a richer schema is not a requirement to clone all of it.

Pending [Justin read-access requests](https://github.com/cbusillo/odoo-tenant-cm/issues/167#issuecomment-6137275857) cover both his sync and cm_data build code. If access arrives, record on #126 what they reveal about source joins, field meanings, timestamps, `[FB:part]`, `employee_output`, deleted rows and corrections. Read to understand; never copy his code. Do not invent equivalent derived tables before their semantics are established. This is not a wait for the independent own-sync fixes.

Confirmed direct-field gap: invoices discard `balance_due`, `amount_paid` and `is_recurring`, present in the current official response and live invoice list. This patch stores them; old invoices require a later parent refresh for historical values. cm_data line-item `user_id` and `line_discount_percent` are not present in the inspected parent-line response or its published example; their source is unresolved, so they are not synthesized. Our monetary fields retain the existing FloatField convention; no precision conversion is claimed.

The live `/users` list reported 44 current entries, compared with our 50 and CM's 86 retained users. Its list uses row arrays, supported by our client. This does not prove 36 users are currently retrievable or lost by pagination. Contacts, estimates, deleted lines and invoice selection differences likewise need retention/build provenance before interpreting one copy as truth.

A related source defect creates anonymous embedded-property records on every update. Our database has **74,240,234 customer-property rows** for 155 customers and 270 contacts, and 454,537 ticket-property rows for 179,831 tickets. The patch updates each parent's existing property row. It neither deletes orphan rows nor resets the database. Cleanup requires a separate exact production plan.

## Official API and release audit

Read October 12: [official API help](https://repair.uservoice.com/knowledgebase/articles/376312-repairshopr-re), [current Swagger JSON](https://api-docs.repairshopr.com/swagger.json), [release archive](https://www.repairshopr.com/blog/categories/release-notes), and the vendor blog. The public archive still ends at April 2024, and the latest blog announcement is the May 2025 Organizations terminology change. No dated recent invoice-line fix was established. Current contracts establish what can be requested; they do not establish a rollout date. The earlier [#126 classification](https://github.com/cbusillo/repairshopr_api/issues/126#issuecomment-6030403985) holds the detailed dated-announcement assessment.

| Contract or unused capability | Our use / action |
| --- | --- |
| Estimates `updated_after`, `created_after` | Updated filter and full incremental pagination already fixed by #127; creation filter is not needed for a mirror. |
| Tickets `since_updated_at`; deprecated `all_comments` | #127 uses every page of `/tickets/{id}/comments` instead of embedded first-comment histories. |
| Per-ticket comments `updated_after/before`, `created_after/before`, sorting, `per_page`, `comment_format` | Complete parent refresh uses pagination and stable creation sorting without date cutoffs. Comment date filters would omit old siblings; optional rich/original formats are unused. |
| Flat `/ticket_comments`, ticket filters and comment-created filters | Potentially fewer historical requests; a bounded old-comment GET timed out with HTTP 504. We retain per-ticket recovery rather than assume the flat endpoint is reliable or captures edited old comments. |
| Invoices `since_updated_at`, `per_page` | Incremental parent selection already supported; it cannot catch children of unchanged parents. Parent recovery has no date cutoff. |
| Line items `invoice_id`, `estimate_id`, not-null filters; paginated metadata | Parent-filtered complete reads are authoritative for recovery. No documented line-item date or stable-sort filter is invented. Bulk totals remain forensic telemetry. |
| Products/customers `sort`; no documented incremental cutoff | Existing windows and their limits remain in [incremental-pagination.md](incremental-pagination.md). No arbitrary filter change is justified by identical current product data. A window does not guarantee every edited old row is captured. |
| Invoice payment-summary fields | Added `amount_paid`, `balance_due`, `is_recurring`. Other list metadata (schedule, external accounting IDs and signatures) is not needed for this bounded gap repair. |
| Ticket asset-name/serial, parent-ID and saved-view filters | Existing `params` forwarding can use these; filtering the mirror by them is not needed. |
| Ticket timers, timelogs, appointments, assets, contracts, part orders, leads, purchase orders, serials/SKUs, schedules, vendors, worksheets, wiki | Not collected by this seven-parent-model sync. No measured table gap establishes that these should be added now. `employee_output` cannot be substituted with a timer endpoint without provenance. |
| Customers renamed Organizations | API still uses `/customers`; no model rename needed. |
| Rate limit | Official help says **180 requests/minute per IP**. Client keeps 150/minute headroom and now waits at, rather than after, its configured limit. Multiple clients on one IP still share the vendor limit; HTTP 429 retries remain. |

The first diagnostic used urllib's request shape and returned HTTP 403. Retrying with the production client's `requests` header/user-agent shape succeeded for invoices, parent line items and per-ticket comments. No credential, identity or access was changed. Credentials were used only inside the existing container; source responses were projected to IDs/keys/counts and kept private.

## Delivery and remaining proof

This change fixes future parent imports, prevents property growth, stores three invoice fields, and prepares `refresh_related` for bounded historical child recovery. See the [operations runbook](ops/repairshopr-sync-confidence-runbook.md#bounded-historical-child-recovery). Full bootstrap now reads line items per invoice: at the measured 176,910 invoices and 150 requests/minute, invoice child calls alone have a theoretical minimum near **20 hours**, before other requests, retries or processing. Use bounded historical batches rather than reset/rebuild production to fix this gap.

No production recovery, cleanup or promotion was performed. #92 remains open until exact live ID coverage is reconciled or a difference is justified. #103 owns testing isolation, gated release and runtime qualification. The source PR is not proof that either lane runs it or that historical data is repaired.
