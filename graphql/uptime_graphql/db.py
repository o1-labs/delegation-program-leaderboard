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

from datetime import UTC, datetime

from psycopg_pool import AsyncConnectionPool

UPTIME_SQL = """
WITH w AS (SELECT max(batch_end_epoch) AS end_epoch FROM bot_logs),
win AS (
    SELECT b.id, b.batch_end_epoch
    FROM bot_logs b, w
    WHERE b.batch_start_epoch >= w.end_epoch - %(seconds)s
      AND b.batch_end_epoch <= w.end_epoch
      AND b.files_processed > -1
),
surveys AS (SELECT count(*) AS n FROM win),
nd AS (SELECT id, block_producer_key AS key FROM nodes WHERE block_producer_key = ANY(%(keys)s)),
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
-- nodes has no unique key on block_producer_key. If one key has several
-- rows, take the row with the most points: its official score, at most 100 percent.
pts AS (
    SELECT nd.key, max(per_node.points) AS points, max(per_node.last_point_end) AS last_point_end
    FROM per_node JOIN nd ON nd.id = per_node.node_id
    GROUP BY 1
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

NODES_SQL = """
SELECT DISTINCT ON (block_producer_key)
       block_producer_key, score, score_percent, updated_at, application_status
FROM nodes
WHERE block_producer_key = ANY(%(keys)s)
ORDER BY block_producer_key, updated_at DESC NULLS LAST
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


def epoch_to_utc(epoch):
    return None if epoch is None else datetime.fromtimestamp(epoch, tz=UTC)


def naive_to_utc(value):
    # submissions.submitted_at is TIMESTAMP without time zone, written in UTC.
    return None if value is None else value.replace(tzinfo=UTC)


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

    async def last_batch_end(self):
        rows = await self._fetch(LAST_BATCH_SQL)
        return rows[0][0]
