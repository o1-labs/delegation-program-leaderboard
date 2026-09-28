# uptime-graphql

Internal, read-only GraphQL API over the Delegation Program coordinator
database. For each block producer (BP) it gives:

- uptime over the last day, week and month;
- whether the BP is up now (it sent a submission recently);
- the official 90-day score that the coordinator stores;
- an activity histogram over a custom date range, to tell a BP that shut
  its node down from a BP that runs a node with problems.

Single container: Strawberry GraphQL on Starlette/uvicorn, port 8080.
The deployment puts it behind the o1labs oauth2-proxy (internal only).

## Endpoints

| Path | Purpose |
|---|---|
| `POST /graphql` | GraphQL API. `GET /graphql` in a browser opens GraphiQL. |
| `GET /healthz` | Liveness: the process runs. Does not touch the database. |
| `GET /readyz` | Readiness: `SELECT 1` on the database, else `503`. |

## Example

```graphql
{
  meta { lastBatchEnd isUpWindowMinutes }
  blockProducer(publicKey: "B62q...") {
    isUp
    lastSubmissionAt
    day: uptime(window: DAY) { percent points batches }
    week: uptime(window: WEEK) { percent }
    month: uptime(window: MONTH) { percent lastPointAt }
    officialScore { scorePercent updatedAt }
  }
  blockProducers(first: 100, applicationStatus: true) {
    items { publicKey isUp month: uptime(window: MONTH) { percent } }
    nextCursor
  }
}
```

## Activity histogram: shut down, or problems?

```graphql
{
  blockProducer(publicKey: "B62q...") {
    activity(from: "2026-09-01T00:00:00Z", to: "2026-09-15T00:00:00Z", bucket: HOUR) {
      totals { submissions acceptedSubmissions failedSubmissions batches points percent
               bucketsWithSubmissions bucketCount }
      buckets { start submissions acceptedSubmissions failedSubmissions batches points percent }
      silences(minMinutes: 60) { start end minutes openEnded }
      longestSilence { start end minutes openEnded }
    }
  }
}
```

- `bucket`: `BATCH` (20 min, one coordinator batch), `HOUR` or `DAY`. The
  range is widened to whole buckets and ends at most at the current time.
  `from`/`to` without a time zone are UTC.
- Each bucket counts the submissions of the BP (all / `accepted`: verified
  without error, the ones the coordinator scores / `failed`: verified false or
  a validation error; the rest is not verified yet), the coordinator batches
  that start in the bucket, and the batches in which the BP earned its point.
- A **silence** is a period without any submission. The range start and end
  count as its limits, so a BP that never submitted has one silence over the
  whole range. `openEnded` means the BP did not come back before `to`.

How to read it:

| Pattern | Likely cause |
|---|---|
| One long silence, `openEnded`, submissions and points 0 after it | Node shut down (or the uptime submission turned off) |
| One long silence that closes, then normal buckets | Outage or maintenance, node came back |
| Submissions in (almost) every bucket, many `failedSubmissions` | Node runs, but its submissions fail verification (wrong version, SNARK work problems, fork mismatch) |
| Submissions accepted, but `points` < `batches` | Node runs, but its blocks are not on the chain the coordinator selects (sync or fork problems) |
| Many short silences | Unstable node or network: restarts, crashes, connectivity |

Two BPs can have the same uptime percent with different causes; the test
suite has one example of each (`B62qshutdown`, `B62qflaky`: both 50.34%).

## What the numbers mean

**Uptime** (`uptime(window:)`) uses the formula of the official score
(`DB.update_scoreboard` in o1-labs/uptime-service-validation), over a
shorter window:

    percent = trunc(points * 100 / batches, 2)

- `batches`: the coordinator's 20-minute batches (`bot_logs`) in the window,
  without batches that a score correction excluded (`files_processed = -1`).
- `points`: the batches in which the BP earned its point (`points_summary`).
- The window is 1, 7 or 30 days and **ends at the end of the latest batch**
  (`meta.lastBatchEnd`), not at the current time. The coordinator runs
  behind real time; the batch in progress does not count against the BP.
- If `nodes` has more than one row for a key, the row with the most points
  counts.

**isUp** is true if the last submission of the BP (`submissions`) is at most
`IS_UP_WINDOW_MINUTES` old (default 40 = two survey intervals). Override it
per query with `isUp(withinMinutes: N)`, 1 to 1440. The submission is not
necessarily verified yet: a BP can be up and still earn no points (for
example when verification fails). Use `uptime(...).lastPointAt` to see the
last batch that scored.

**blockProducers** lists the BPs in `nodes` (BPs that the coordinator has
scored at least once), ordered by public key. `blockProducer(publicKey:)`
also finds a BP that has only submissions; it returns null for an unknown key.

## Environment

| Variable | Required | Default | Notes |
|---|---|---|---|
| `POSTGRES_HOST` | yes | | |
| `POSTGRES_PORT` | no | `5432` | |
| `POSTGRES_DB` | yes | | the coordinator database |
| `POSTGRES_USER` | yes | | use the read-only user (`o1labs-ro`) |
| `POSTGRES_PASSWORD` | yes | | |
| `POSTGRES_SSLMODE` | no | `prefer` | |
| `IS_UP_WINDOW_MINUTES` | no | `40` | 1 to 1440 |
| `MAX_PAGE_SIZE` | no | `500` | largest `first` in `blockProducers` |
| `MAX_QUERY_DEPTH` | no | `8` | the deepest useful query has depth 3 |
| `STATEMENT_TIMEOUT_MS` | no | `10000` | per SQL statement |
| `DB_POOL_MAX_SIZE` | no | `4` | connections per pod |
| `MAX_ACTIVITY_DAYS` | no | `92` | longest `activity` range |
| `MAX_ACTIVITY_BUCKETS` | no | `2500` | most buckets in one `activity` |
| `MAX_REQUEST_BUCKETS` | no | `50000` | most buckets of all `activity` fields in one request |

The service also opens its sessions with `default_transaction_read_only=on`,
so it cannot write even with a read-write user.

## Performance

Measured on PostgreSQL 16 with 300 BPs, 90 days of batches (1.75M
`points_summary` rows) and 2.6M `submissions` rows: one query for all 300
BPs with the three windows, `isUp` and `officialScore` takes about 175 ms.
The queries use only existing indexes (`uq_ps_bot_log_node`,
`idx_submissions_submitter_datetime`). A per-request DataLoader makes one
SQL query per field and argument set, not one per BP.

`activity` over 30 days, same data:

| Request | Time |
|---|---|
| 1 BP, `HOUR` buckets, silences, longest silence | 0.1 s |
| 300 BPs, `DAY` buckets and totals | 1.6 s |
| 50 BPs, `HOUR` buckets | 2.2 s |
| 300 BPs, longest silence | 3.5 s |

300 BPs with `HOUR` buckets (216,000 buckets) is refused by
`MAX_REQUEST_BUCKETS`; ask for a smaller page or a larger bucket.

## Tests

```bash
./run-tests.sh
```

The tests start PostgreSQL in Docker (testcontainers), create the tables
this service reads (`tests/schema.sql`, copied from the coordinator) and
check the numbers against a seeded month of batches.

## Local run

```bash
docker build -t uptime-graphql:dev .
docker run --rm -p 8080:8080 \
  -e POSTGRES_HOST=host.docker.internal -e POSTGRES_DB=coordinator \
  -e POSTGRES_USER=o1labs-ro -e POSTGRES_PASSWORD=secret \
  uptime-graphql:dev
open http://localhost:8080/graphql
```

## Published image

`ghcr.io/o1-labs/uptime-graphql:<tag>`, pushed by
`.github/workflows/graphql-image.yml`: `main-<sha>` on merge to `main`,
`vX.Y.Z` on a `graphql-vX.Y.Z` tag.
