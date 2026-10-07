# Incremental pagination

`Client.get_model` sends `updated_after` for Estimate and `since_updated_at`
for other models when given a checkpoint. It reads every result page unless
its caller explicitly supplies `num_last_pages`. The sync command supplies
a last-page window for Customer, Payment and Product. These windows are
workarounds for endpoints that ignore the incremental filter, rather than
limits on a filtered change set. Estimates now read every filtered page.

## Live comparison

A read-only check for [issue #100](https://github.com/cbusillo/repairshopr_api/issues/100)
on 2026-10-03 at 12:43–12:45 UTC made twelve first-page GET requests using the
existing read-only token in place. No credentials or record contents were saved.
Each endpoint was queried without a cutoff, with a cutoff one hour earlier,
and with a cutoff one day in the future. Customer and Product used the sync's
`sort=updated_at ASC`; Estimate and Payment used no sort parameter. All twelve
responses returned HTTP 200.

| Endpoint | Unfiltered total entries | One-hour cutoff | Future cutoff | Rows on future-cutoff page |
| --- | ---: | ---: | ---: | ---: |
| customers | 155 | 155 | 155 | 100 |
| estimates | 25,075 | 25,075 | 25,075 | 25 |
| payments | 13,446 | 13,446 | 13,446 | 25 |
| products | 2,370 | 2,370 | 2,370 | 20 |

The one-hour cutoff was `2026-10-03T11:43:47.853146Z`; the future cutoff was
`2026-10-04T12:44:53.585308Z`. Under the future cutoff, all returned Customer,
Estimate and Payment rows had `updated_at` older than the one-hour cutoff.
Product rows exposed no `updated_at` field, but still returned a nonempty page
under the future cutoff. The counts above are the API's reported metadata,
not an independent inventory.

For this account and request shape, all four endpoints failed to apply
`since_updated_at`. At that time their windows were: page 1 plus the last ten
pages for Customer, one for Estimate, and two for Payment and Product. Initial
and baseline imports disable the windows and read every page. Invoice, Ticket
and User have no window configured; this check did not test their server-side
filter behavior. The client test
`test_get_model_paginates_and_formats_since_updated_at` exercises the
unwindowed incremental path and fails if it skips a result page.

## Current estimate contract

The [vendor API specification](https://api-docs.repairshopr.com/swagger.json)
read for [issue #126](https://github.com/cbusillo/repairshopr_api/issues/126)
documents `updated_after` for `GET /estimates`. The comparison above tested
`since_updated_at`, so it does not establish whether the documented estimate
filter works. The client now uses `updated_after` and the sync removes the
estimate window to avoid dropping middle pages of a filtered change set.
If the server ignores that documented filter too, every estimate page will
be read each cycle, increasing API traffic. No live verification was run for
this source change; the HTTP-faked Django regression covers the documented
request and imports a change set spanning four pages.

## Limits and rechecking

The windows do not guarantee that an older record changed outside the window
will be imported. They avoid fetching the entire unfiltered dataset each cycle;
this check does not establish complete historical coverage or repair previously
missing records. The separate invoice-line-item investigation remains on
[issue #92](https://github.com/cbusillo/repairshopr_api/issues/92).

Recheck the same request shape before changing these windows if RepairShopr's
filter behavior changes or another account is used. For an endpoint proven to
honor the filter, remove its window so every incremental page is read. A future
cutoff helps distinguish filtering from unchanged metadata: a nonempty response
containing older records cannot be a correctly filtered result.

## Ticket comment completeness

The current vendor specification deprecates `all_comments` on `GET /tickets`
and names March 31, 2026 as the transition to returning only the first
comment. The sync fetches all pages of `GET /tickets/{id}/comments` for every
ticket it imports before replacing that ticket's comment relations. This adds
API requests, using the existing client rate limit and retry behavior. A failed
comment page fails the cycle before replacing that ticket's relations or
advancing the checkpoint. The client library's `Ticket.comments` field still
reflects the response it receives; `Client.fetch_ticket_comments` explicitly
retrieves the full history.

Comment reads have no date cutoff: replacing relations from only recently
changed comments would detach older comments. Tickets outside the current
incremental selection are not backfilled by this change, and independently
edited comments whose parent ticket is not returned are not discovered.
Historical recovery needs a separately authorized full import or targeted
backfill; no live import accompanies the source fix.
