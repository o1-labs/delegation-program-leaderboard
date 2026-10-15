"""Read-only queries on the coordinator database.

The tables are written by two other services:
  * uptime-service-backend inserts one `submissions` row per submission;
  * the coordinator (o1-labs/uptime-service-validation) writes one `bot_logs`
    row per 20-minute batch and, through a trigger on `points`, one
    `points_summary` row per (batch, BP) in which the BP earned its point.

Uptime uses the formula of the coordinator's DB.update_scoreboard and of its
score-correction tasks: over the batches in the window,

    percent = trunc(points * 100 / batches, 2)

where `batches` counts the batches with files_processed > -1 (a score
correction sets -1 to take a batch out of the score) and `points` counts the
BP's points_summary rows in those batches. The window ends at the end of the
latest batch, not at now(): the coordinator runs behind real time, and the
batch in progress must not count as a batch without a point.

Every function takes a list of keys and returns one result per key, in the
same order, so that the GraphQL layer can batch lookups with a DataLoader.
"""

from datetime import UTC, datetime, timedelta

from psycopg_pool import AsyncConnectionPool

# nodes has no unique key on block_producer_key, so one rule picks one row per
# key for every field: the highest score, then the lowest id. The coordinator
# cannot add points to a duplicated key (its points INSERT looks the node_id
# up with a scalar subquery, which fails on two rows), so the points of a
# duplicate are history, and the scored row is the one the official score
# reports. Not the newest row: update_scoreboard never sets updated_at,
# which is the creation time of the row.
NODE_ROWS = """
SELECT DISTINCT ON (block_producer_key)
       id, block_producer_key AS key, score, score_percent, updated_at, application_status
FROM nodes
{where}
ORDER BY block_producer_key, score DESC NULLS LAST, id
"""

KEYS_NODES = NODE_ROWS.format(where="WHERE block_producer_key = ANY(%(keys)s)")

UPTIME_SQL = f"""
WITH w AS (SELECT max(batch_end_epoch) AS end_epoch FROM bot_logs),
win AS (
    SELECT b.id, b.batch_end_epoch
    FROM bot_logs b, w
    WHERE b.batch_start_epoch >= w.end_epoch - %(seconds)s
      AND b.batch_end_epoch <= w.end_epoch
      AND b.files_processed > -1
),
surveys AS (SELECT count(*) AS n FROM win),
nd AS ({KEYS_NODES}),
-- Count per node_id, like update_scoreboard: (bot_log_id, node_id) is unique
-- in points_summary, so count(*) needs no DISTINCT (a DISTINCT over a month
-- of batches sorts ~0.5M rows for 300 BPs and is 5x slower).
per_node AS (
    SELECT ps.node_id, count(*) AS points, max(win.batch_end_epoch) AS last_point_end
    FROM points_summary ps
    JOIN win ON win.id = ps.bot_log_id
    WHERE ps.node_id IN (SELECT id FROM nd)
    GROUP BY 1
),
pts AS (
    SELECT nd.key, per_node.points, per_node.last_point_end
    FROM per_node JOIN nd ON nd.id = per_node.node_id
)
SELECT k.key, COALESCE(pts.points, 0), surveys.n, pts.last_point_end, w.end_epoch
FROM unnest(%(keys)s::text[]) AS k(key)
LEFT JOIN pts ON pts.key = k.key
CROSS JOIN surveys
CROSS JOIN w
"""

# One index probe per key on idx_submissions_submitter_datetime
# (submitter, submitted_at DESC).
LAST_SUBMISSION_SQL = """
SELECT k.key, s.submitted_at
FROM unnest(%(keys)s::text[]) AS k(key)
LEFT JOIN LATERAL (
    SELECT submitted_at FROM submissions
    WHERE submitter = k.key
    ORDER BY submitted_at DESC
    LIMIT 1
) s ON true
"""

NODE_COLUMNS = "key, score, score_percent, updated_at, application_status"

NODES_SQL = f"SELECT {NODE_COLUMNS} FROM ({KEYS_NODES}) n"

SCOREBOARD_SQL = f"""
SELECT {NODE_COLUMNS} FROM ({NODE_ROWS.format(where="")}) n
WHERE (%(status)s::boolean IS NULL OR application_status = %(status)s::boolean)
  AND (NOT %(scored_only)s OR score IS NOT NULL)
ORDER BY score_percent DESC NULLS LAST, score DESC NULLS LAST, key
"""

LIST_SQL = """
SELECT DISTINCT block_producer_key
FROM nodes
WHERE block_producer_key > %(after)s
  AND (%(status)s::boolean IS NULL OR application_status = %(status)s::boolean)
ORDER BY 1
LIMIT %(limit)s
"""

LAST_BATCH_SQL = "SELECT max(batch_end_epoch) FROM bot_logs"

# Activity histogram over [start, end) in buckets of `size` seconds; bucket i
# starts at start + i * size. A batch belongs to the bucket in which it starts.
ACTIVITY_BATCHES_SQL = """
SELECT (batch_start_epoch - %(start)s) / %(size)s AS i, count(*)
FROM bot_logs
WHERE batch_start_epoch >= %(start)s AND batch_start_epoch < %(end)s
  AND files_processed > -1
GROUP BY 1
"""

ACTIVITY_POINTS_SQL = f"""
WITH win AS (
    SELECT id, (batch_start_epoch - %(start)s) / %(size)s AS i
    FROM bot_logs
    WHERE batch_start_epoch >= %(start)s AND batch_start_epoch < %(end)s
      AND files_processed > -1
),
nd AS ({KEYS_NODES}),
per_node AS (
    SELECT ps.node_id, win.i, count(*) AS points
    FROM points_summary ps
    JOIN win ON win.id = ps.bot_log_id
    WHERE ps.node_id IN (SELECT id FROM nd)
    GROUP BY 1, 2
)
SELECT nd.key, per_node.i, per_node.points
FROM per_node JOIN nd ON nd.id = per_node.node_id
"""

# accepted = what the coordinator scores (coordinator.load_submissions):
# verified and no validation_error. failed = verified false or an error.
# The rest (verified IS NULL, no error) is not verified yet. floor(): a cast
# to bigint rounds, which moves a submission in the last half second of a
# bucket into the next one (or past the last one). date_part() is double
# precision, which is exact to the microsecond here and 25% faster than the
# numeric extract().
ACTIVITY_SUBMISSIONS_SQL = """
SELECT submitter,
       (floor(date_part('epoch', submitted_at))::bigint - %(start)s) / %(size)s AS i,
       count(*),
       count(*) FILTER (WHERE verified AND coalesce(validation_error, '') = ''),
       count(*) FILTER (WHERE verified IS FALSE OR coalesce(validation_error, '') <> '')
FROM submissions
WHERE submitter = ANY(%(keys)s)
  AND submitted_at >= %(start_ts)s AND submitted_at < %(end_ts)s
GROUP BY 1, 2
"""

# Gaps between consecutive submissions of each key in [start_ts, end_ts).
# The range start counts as a submission before the first one and the range
# end as one after the last one, so a silence at either end is a gap too, and
# a key with no submission has one gap over the whole range. Returns the gaps
# of at least min_gap and the longest gap(s) of each key (is_longest).
#
# Per key (LATERAL) so that each window runs over one BP's rows only;
# lead() over submitted_at DESC follows idx_submissions_submitter_datetime and
# needs no sort, and the trailing gap is a top-1 lookup on the same index.
# 300 BPs x 30 days (2.5M submissions) take about 2.6 s.
SILENCES_SQL = """
SELECT k.key, x.gap_start, x.gap_end, x.gap = x.longest
FROM unnest(%(keys)s::text[]) AS k(key)
CROSS JOIN LATERAL (
    SELECT gap_start, gap_end, gap_end - gap_start AS gap, max(gap_end - gap_start) OVER () AS longest
    FROM (
        SELECT lead(submitted_at, 1, %(start_ts)s::timestamp) OVER (ORDER BY submitted_at DESC) AS gap_start,
               submitted_at AS gap_end
        FROM submissions
        WHERE submitter = k.key AND submitted_at >= %(start_ts)s AND submitted_at < %(end_ts)s
        UNION ALL
        SELECT coalesce(
                   (SELECT max(submitted_at) FROM submissions
                    WHERE submitter = k.key AND submitted_at >= %(start_ts)s AND submitted_at < %(end_ts)s),
                   %(start_ts)s::timestamp),
               %(end_ts)s::timestamp
    ) g
    WHERE gap_end > gap_start
) x
WHERE x.gap >= %(min_gap)s OR x.gap = x.longest
ORDER BY 1, 2
"""


def epoch_to_utc(epoch):
    return None if epoch is None else datetime.fromtimestamp(epoch, tz=UTC)


def naive_to_utc(value):
    # submissions.submitted_at is TIMESTAMP without time zone, written in UTC.
    return None if value is None else value.replace(tzinfo=UTC)


def utc_to_naive(value):
    return value.astimezone(UTC).replace(tzinfo=None)


def percent(points, batches):
    """trunc(points * 100 / batches, 2), in integer arithmetic."""
    if not batches:
        return None
    return (points * 10_000 // batches) / 100


class Database:
    def __init__(self, settings):
        options = f"-c default_transaction_read_only=on -c statement_timeout={settings.statement_timeout_ms}"
        self.pool = AsyncConnectionPool(
            settings.conninfo,
            min_size=1,
            max_size=settings.pool_max_size,
            # Wait for a free connection at most this long, so /readyz fails
            # fast when the database is down.
            timeout=5,
            kwargs={"autocommit": True, "options": options},
            open=False,
        )

    async def open(self):
        await self.pool.open()

    async def close(self):
        await self.pool.close()

    async def _fetch(self, query, params=None):
        async with self.pool.connection() as conn:
            cur = await conn.execute(query, params)
            return await cur.fetchall()

    async def ping(self):
        await self._fetch("SELECT 1")

    async def uptime(self, keys, days):
        """-> [(points, batches, last_point_end, window_end)] per key."""
        rows = await self._fetch(UPTIME_SQL, {"keys": list(keys), "seconds": days * 86400})
        by_key = {row[0]: row[1:] for row in rows}
        return [by_key[key] for key in keys]

    async def last_submission(self, keys):
        rows = await self._fetch(LAST_SUBMISSION_SQL, {"keys": list(keys)})
        by_key = {key: naive_to_utc(at) for key, at in rows}
        return [by_key[key] for key in keys]

    async def nodes(self, keys):
        """-> [(score, score_percent, updated_at, application_status) | None] per key."""
        rows = await self._fetch(NODES_SQL, {"keys": list(keys)})
        by_key = {row[0]: row[1:] for row in rows}
        return [by_key.get(key) for key in keys]

    async def list_keys(self, after, limit, application_status):
        rows = await self._fetch(
            LIST_SQL, {"after": after or "", "limit": limit, "status": application_status}
        )
        return [row[0] for row in rows]

    async def scoreboard(self, application_status, scored_only):
        """-> [(key, score, score_percent, updated_at, application_status)], best first."""
        return await self._fetch(SCOREBOARD_SQL, {"status": application_status, "scored_only": scored_only})

    async def last_batch_end(self):
        rows = await self._fetch(LAST_BATCH_SQL)
        return rows[0][0]

    async def activity(self, keys, start, end, size):
        """Histogram over [start, end) (epoch seconds, buckets of `size`).

        -> per key: list of [submissions, accepted, failed, batches, points]
        per bucket.
        """
        params = {
            "keys": list(keys),
            "start": start,
            "end": end,
            "size": size,
            "start_ts": utc_to_naive(epoch_to_utc(start)),
            "end_ts": utc_to_naive(epoch_to_utc(end)),
        }
        count = (end - start) // size
        batches = [0] * count
        for i, n in await self._fetch(ACTIVITY_BATCHES_SQL, params):
            batches[i] = n
        result = {key: [[0, 0, 0, batches[i], 0] for i in range(count)] for key in keys}
        for key, i, n in await self._fetch(ACTIVITY_POINTS_SQL, params):
            result[key][i][4] = n
        for key, i, n, accepted, failed in await self._fetch(ACTIVITY_SUBMISSIONS_SQL, params):
            result[key][i][0:3] = [n, accepted, failed]
        return [result[key] for key in keys]

    async def silences(self, keys, start_ts, end_ts, min_minutes):
        """-> per key: [(gap_start, gap_end, is_longest)] in UTC, by gap_start."""
        rows = await self._fetch(
            SILENCES_SQL,
            {
                "keys": list(keys),
                "start_ts": utc_to_naive(start_ts),
                "end_ts": utc_to_naive(end_ts),
                "min_gap": timedelta(minutes=min_minutes),
            },
        )
        result = {key: [] for key in keys}
        for key, gap_start, gap_end, longest in rows:
            result[key].append((naive_to_utc(gap_start), naive_to_utc(gap_end), longest))
        return [result[key] for key in keys]
