# Metrics reference

This document defines every metric exposed by `uptime-navigator-lite`,
pinpoints the code path that computes it, and calls out where the
definition differs (or matches) the production delegation program
(`o1-labs/uptime-service-validation`).

For the broader scope/caveat of the lite stack, see
[issue #9 — *lite/ verifier: best-effort metrics only — not suitable for
payouts/audit*](https://github.com/o1-labs/delegation-program-leaderboard/issues/9).

---

## Data sources

Every metric is derived from one table:

| Source | What's in it | Written by |
|---|---|---|
| `submissions` (PostgreSQL) | One row per uptime POST a Mina block producer makes to `/v1/submit` | `o1-labs/uptime-service-backend` (`src/delegation_backend/postgres.go`, `insertSubmissionWithoutSnarkWork` / `insertSubmissionWithSnarkWork`) |

The backend persists only a subset of the submitted payload: outer
envelope fields (`submitted_at`, `submitter`, `block_hash`, `remote_addr`,
`peer_id`, `built_with_commit_sha`, optional `snark_work` blob). It does
NOT decode the binary payload, so `state_hash` / `height` / `slot` /
`parent` columns are present in the schema (created by
`uptime-postgresql.yaml.gotmpl`'s `00-create-submissions.sql`) but
stay `NULL`.

Two columns are filled by the lite **verifier**, not the backend:

| Column | Set by | When |
|---|---|---|
| `verified` (boolean) | `lite/api/verifier.py` | Every `*/10 min` CronJob run |
| `block_creator` (text) | `lite/api/verifier.py` | Same |
| `validation_error` (text) | `lite/api/verifier.py` | Same |

The verifier adds the `block_creator` column on startup if it's missing
(`lite/api/verifier.py:ensure_schema`).

---

## Endpoint → metric map

| Endpoint | Metric(s) | Computed in |
|---|---|---|
| `GET /api/submitters` | submission counts, valid/invalid, on/off/pending-chain counts, blocks_produced | `lite/api/app.py:submitters` |
| `GET /api/submitter/<pk>` | most recent 100 rows for one BP | `lite/api/app.py:submitter` |
| `GET /api/summary` | daily submission counts per BP | `lite/api/app.py:summary` |
| `GET /api/uptime/<pk>` | per-bucket activity over a window + coverage % | `lite/api/app.py:uptime` |
| `GET /api/leaderboard` | production-equivalent score and score_percent | `lite/api/app.py:leaderboard` |
| `GET /healthz` | DB connectivity probe | `lite/api/app.py:healthz` |

---

## Definitions

### Per-submitter aggregates (`/api/submitters`)

For each distinct `submitter`, the API returns counts derived from a
single `GROUP BY submitter` query (`lite/api/app.py:submitters`):

| Field | SQL fragment | Meaning |
|---|---|---|
| `submissions` | `COUNT(*)` | Every row this BP has in the table, no time bound. |
| `first_seen` | `MIN(submitted_at)` | First submission ever recorded. |
| `last_seen` | `MAX(submitted_at)` | Most recent submission. |
| `valid` | `COUNT(*) FILTER (WHERE validation_error IS NULL)` | Rows the verifier didn't mark with an error (includes pre-verifier rows where `validation_error` is NULL by default). |
| `invalid` | `COUNT(*) FILTER (WHERE validation_error IS NOT NULL)` | Rows the verifier rejected. |
| `chain_verified` | `COUNT(*) FILTER (WHERE verified IS TRUE)` | Rows the verifier confirmed had a best-chain block near `submitted_at`. |
| `chain_rejected` | `COUNT(*) FILTER (WHERE verified IS FALSE)` | Rows the verifier examined and rejected (no best-chain block in window). |
| `chain_pending` | `COUNT(*) FILTER (WHERE verified IS NULL)` | Rows the verifier hasn't yet processed. |
| `blocks_produced` | `COUNT(*) FILTER (WHERE block_creator = submitter)` | Rows where the verifier observed that the closest best-chain block was created by this BP. |

`valid`/`invalid` are legacy column semantics inherited from the
schema; `chain_*` reflect the lite verifier's writes.

### Per-submission detail (`/api/submitter/<pk>`)

Returns the last 100 rows for one BP, ordered `submitted_at DESC`. Same
columns as the `submissions` table directly, including verifier-written
`verified` / `block_creator` / `validation_error`. Implementation:
`lite/api/app.py:submitter`.

### Per-day counts (`/api/summary`)

`GROUP BY (submitted_at::date, submitter)`. One row per `(day, submitter)`
with `submissions` count. Implementation: `lite/api/app.py:summary`.

### Bucketed activity over a window (`/api/uptime/<pk>`)

Inputs:
- `window` — hours (clamped to `[1, 168]`, default `24`)
- `bucket_minutes` — bucket width in minutes (clamped to `[1, 60]`, default `5`)

Implementation: `lite/api/app.py:uptime`. The SQL produces every
`bucket_minutes`-wide bucket between `LOCALTIMESTAMP - window` and
`LOCALTIMESTAMP` via `generate_series`, then `LEFT JOIN`s submissions
into the bucket whose `[start, start + bucket_minutes)` interval
contains each `submitted_at`. This avoids the alignment bug that an
earlier `(minute % bucket_minutes)` approach had.

Returns:

| Field | Definition |
|---|---|
| `buckets[].bucket_start` | Window start of the bucket, ISO 8601 |
| `buckets[].submissions` | Count of rows with `submitted_at` in `[bucket_start, bucket_start + bucket_minutes)` |
| `buckets[].chain_verified` | Same, filtered to `verified IS TRUE` |
| `coverage_pct` | `100.0 * (count of buckets with submissions > 0) / total_buckets` |
| `chain_verified_pct` | `100.0 * (count of buckets with chain_verified > 0) / total_buckets` |

This is a **diagnostic** metric: "did the BP submit at least once during
each N-minute window in the last M hours?" It is NOT the production
score (see next).

### Score and score_percent (`/api/leaderboard`)

**This is the production-equivalent metric.** The SQL in
`lite/api/app.py:leaderboard` mirrors
`uptime-service-validation/uptime_service_validation/coordinator/helper.py:update_scoreboard`
byte-for-byte:

```sql
-- Production formula (helper.py:262-298, simplified):
WITH epochs AS (start_date = snapshot - uptime_days),
     surveys AS (SELECT count(*) FROM bot_logs
                 WHERE batch_*_epoch in window AND files_processed > -1),
     scores  AS (SELECT node_id, count(bot_log_id) AS bp_points
                 FROM points_summary p JOIN bot_logs b ON p.bot_log_id=b.id
                 WHERE b.batch_*_epoch in window
                 GROUP BY node_id)
UPDATE nodes SET score = bp_points,
                 score_percent = trunc(bp_points * 100.0 / surveys, 2)
```

```sql
-- Lite (app.py:leaderboard):
WITH buckets AS (generate_series of survey_interval_minutes from
                 LOCALTIMESTAMP - uptime_days through LOCALTIMESTAMP),
     bucket_count AS (SELECT count(*) FROM buckets),
     scores  AS (SELECT submitter,
                        count(DISTINCT bucket_start) AS score
                 FROM buckets b JOIN submissions s
                   ON s.submitted_at >= b.bucket_start
                  AND s.submitted_at <  b.bucket_start + bucket
                  AND s.verified IS TRUE          -- strict by default
                 GROUP BY submitter)
SELECT submitter,
       score,
       trunc(score * 100.0 / total_buckets, 2) AS score_percent,
       total_buckets AS surveys
```

Mapping table:

| Production concept | Lite equivalent |
|---|---|
| `bot_logs` row (one per coordinator iteration) | one bucket from `generate_series` |
| `points_summary` row (BP scored a survey) | a row in `submissions` for this BP whose `submitted_at` falls in the bucket |
| `points_summary.bot_log_id` constraint (must be validated) | `s.verified IS TRUE` (when `require_verified=true`, the default) |
| `bot_logs.files_processed > -1` (exclude failed surveys) | **no equivalent** — every bucket counts |

#### Defaults

| Parameter | Default | Production constant |
|---|---|---|
| `uptime_days` | `90` | `Config.UPTIME_DAYS_FOR_SCORE` (`coordinator/config.py:13`) |
| `survey_interval_minutes` | `20` | `Config.SURVEY_INTERVAL_MINUTES` (`coordinator/config.py:11`) |
| `require_verified` | `true` (strict) | n/a — production always uses validated submissions |

Defaults match production. The query string can override for diagnostics.

#### Differences from production

1. **No failed-survey concept.** Production excludes coordinator
   iterations where `files_processed = -1`. Lite counts every bucket as
   a survey opportunity. Effect: lite's `surveys` ≥ production's
   `surveys` for the same period → lite's `score_percent` ≤ production's
   for the same BP behavior. Bounded approximation; never inflated.

2. **No cryptographic validation.** Production's `points_summary` is
   populated by validator workers that decode the binary payload and
   verify the signature. Lite's `verified=true` reflects only the
   temporal verifier (a best-chain block existed within
   `MATCH_WINDOW_SEC` seconds of `submitted_at`). A signed-but-fake
   submission near a real chain block is treated as valid. Tracked in
   [issue #9](https://github.com/o1-labs/delegation-program-leaderboard/issues/9).

3. **No live denominator skew from coordinator outages.** Production's
   denominator only counts surveys the coordinator actually ran. If the
   coordinator was down for a week, the denominator and numerator both
   drop. Lite always uses the theoretical bucket count.

---

## The verifier (how `verified` and `block_creator` get populated)

`lite/api/verifier.py` is a one-shot Kubernetes CronJob. It runs every
`*/10 minutes` and:

1. `SELECT id, submitter, submitted_at FROM submissions WHERE verified IS NULL` (limited by `VERIFIER_BATCH_SIZE`, default 500)
2. For each batch, compute `[min(submitted_at) - W, max(submitted_at) + W]` where `W = VERIFIER_MATCH_WINDOW_SEC` (default 90)
3. Single GraphQL query to `archive-node-api` (path `/`, not `/graphql` — see [memory note](https://github.com/o1-labs/gitops-infrastructure)) for `blocks(query: {dateTime_gte, dateTime_lt, inBestChain: true})`
4. For each row, find best-chain blocks in `[submitted_at - W, submitted_at + W]`:
    - If any block's `creator == submitter`: `verified=true, block_creator=submitter, validation_error=NULL`
    - Else if any block exists: `verified=true, block_creator=<closest block's creator>, validation_error="submission-near-block-not-by-self"`
    - Else: `verified=false, validation_error="no-block-near-submission-time"`
5. Batched `UPDATE submissions` (page_size 500)

We use `inBestChain: true` and **not** `canonical: true` because Mina's
`k=290` finalization depth means archive-node-api wouldn't return any
recent blocks as canonical on a young testnet. `inBestChain` is a
strict superset of canonical on mature chains — see
`coordinator/helper.py:262-298` for the strictness production assumes
(`files_processed > -1` on bot_logs) versus what lite assumes
(every bucket is a survey).

---

## Configuration

### Navigator (Flask) — runtime

| Env var | Required | Notes |
|---|---|---|
| `POSTGRES_HOST` | yes | |
| `POSTGRES_PORT` | no | default `5432` |
| `POSTGRES_DB` | yes | |
| `POSTGRES_USER` | yes | |
| `POSTGRES_PASSWORD` | yes | |
| `POSTGRES_SSLMODE` | no | default `disable` |
| `WHITELIST` | no | comma-separated submitter pubkeys; every endpoint filters to this set |

### Verifier (CronJob) — runtime

| Env var | Required | Notes |
|---|---|---|
| `ARCHIVE_NODE_API_URL` | yes | GraphQL endpoint; **bare base URL**, not `…/graphql` |
| `POSTGRES_*` | yes | same as navigator |
| `VERIFIER_BATCH_SIZE` | no | default `500` rows per loop iteration |
| `VERIFIER_MATCH_WINDOW_SEC` | no | default `90` |
| `VERIFIER_MAX_BATCHES` | no | default `20` (one CronJob run processes up to `BATCH_SIZE * MAX_BATCHES` rows) |
| `VERIFIER_GRAPHQL_TIMEOUT` | no | default `30` |

### Leaderboard query params

| Param | Default | Range |
|---|---|---|
| `uptime_days` | `90` | `[1, 365]` |
| `survey_interval_minutes` | `20` | `[1, 1440]` |
| `require_verified` | `true` | `true` / `false` |

---

## Code map

| Concern | File |
|---|---|
| HTTP routes + SQL | `lite/api/app.py` |
| Chain cross-validator | `lite/api/verifier.py` |
| Static UI | `lite/web/{index.html,app.js,style.css}` |
| Image build | `lite/Dockerfile` |
| Tests + runner | `lite/tests/`, `lite/run-tests.sh` |
| CI (PR + tag image push) | `.github/workflows/lite-image.yml` |
| Production scoring (for reference) | `o1-labs/uptime-service-validation/uptime_service_validation/coordinator/helper.py` (specifically `update_scoreboard`) and `coordinator/config.py` |
| Backend INSERT | `o1-labs/uptime-service-backend/src/delegation_backend/postgres.go` |
| Submissions schema (initdb) | `o1-labs/gitops-infrastructure/platform/o1labs-hetzner-networks/mina-standard-pre-mesa-auto/templates/uptime-postgresql.yaml.gotmpl` |
