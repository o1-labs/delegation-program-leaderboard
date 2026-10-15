"""Request limits, bucket edges and duplicate `nodes` rows.

Each test reproduces a defect found in review of #12.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from starlette.testclient import TestClient

from uptime_graphql.app import create_app
from uptime_graphql.config import Settings
from uptime_graphql.db import Database

from .conftest import ACTIVITY_FROM, BATCH, DAY_BATCHES, END, FLAKY

SUBSECOND = "B62qsubsecond"  # submissions only, so it is in no list or scoreboard
SPLIT = "B62qsplit"  # two nodes rows that disagree


def iso(epoch):
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


class CountingDatabase(Database):
    def __init__(self, settings):
        super().__init__(settings)
        self.silence_queries = 0

    async def silences(self, *args, **kwargs):
        self.silence_queries += 1
        return await super().silences(*args, **kwargs)


SILENCES = """
query ($key: String!, $from: DateTime!, $to: DateTime!) {
  blockProducer(publicKey: $key) {
    activity(from: $from, to: $to) { %s }
  }
}
"""


def run_silences(settings, fields):
    db = CountingDatabase(settings)
    variables = {"key": FLAKY, "from": iso(ACTIVITY_FROM), "to": iso(END)}
    with TestClient(create_app(settings, db=db)) as client:
        result = client.post("/graphql", json={"query": SILENCES % fields, "variables": variables}).json()
    return result, db.silence_queries


def test_silences_and_longest_silence_share_one_query(settings):
    result, queries = run_silences(settings, "silences { minutes } longestSilence { minutes }")
    assert "errors" not in result, result
    assert queries == 1


def test_aliased_silences_cannot_multiply_sql_queries(settings):
    # Each distinct minMinutes is one SILENCES_SQL over every BP of the request.
    fields = " ".join(f"s{m}: silences(minMinutes: {m}) {{ minutes }}" for m in range(61, 81))
    result, queries = run_silences(settings, fields)
    assert "silences" in result["errors"][0]["message"]
    assert queries <= settings.max_silence_queries


@pytest.fixture(scope="module")
def subsecond_submissions(pg):
    # The backend writes whole seconds, but the schema does not enforce it.
    end = datetime.fromtimestamp(END, UTC).replace(tzinfo=None)
    rows = [end - timedelta(milliseconds=400), end - timedelta(hours=1, milliseconds=400)]
    with psycopg.connect(pg.get_connection_url(), autocommit=True) as conn:
        for at in rows:
            conn.execute(
                "INSERT INTO submissions (submitted_at_date, submitted_at, submitter, verified)"
                " VALUES (%s, %s, %s, true)",
                (at.date(), at, SUBSECOND),
            )
        yield
        conn.execute("DELETE FROM submissions WHERE submitter = %s", (SUBSECOND,))


def test_subsecond_submission_stays_in_its_bucket(gql, subsecond_submissions):
    query = """
    query ($key: String!, $from: DateTime!, $to: DateTime!) {
      blockProducer(publicKey: $key) { activity(from: $from, to: $to) { buckets { submissions } } }
    }
    """
    result = gql(query, key=SUBSECOND, **{"from": iso(END - 7200), "to": iso(END)})
    assert "errors" not in result, result["errors"]
    buckets = result["data"]["blockProducer"]["activity"]["buckets"]
    assert [b["submissions"] for b in buckets] == [1, 1]


class HangingDatabase(Database):
    async def ping(self):
        # A peer that stops answering without a reset: the query never returns.
        # On cancel, psycopg tries to cancel it on the server and waits (up to
        # 10 s) before it re-raises.
        try:
            await asyncio.sleep(8)
        except asyncio.CancelledError:
            await asyncio.sleep(3)
            raise


def test_readyz_answers_503_within_5_s_when_the_database_hangs(settings):
    with TestClient(create_app(settings, db=HangingDatabase(settings))) as client:
        started = time.monotonic()
        response = client.get("/readyz")
        elapsed = time.monotonic() - started
    assert response.status_code == 503
    assert elapsed < 6.5


def test_lowest_accepted_depth_runs_the_deepest_documented_query(settings):
    # scoreboard.blockProducer.activity.buckets.start has depth 4.
    base = {"POSTGRES_HOST": "h", "POSTGRES_DB": "d", "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p"}
    lowest = next(d for d in range(1, 21) if _accepts_depth(base, d))
    query = """
    query ($from: DateTime!, $to: DateTime!) {
      scoreboard { blockProducer { activity(from: $from, to: $to, bucket: DAY) { buckets { start } } } }
    }
    """
    shallow = Settings(conninfo=settings.conninfo, max_query_depth=lowest)
    with TestClient(create_app(shallow)) as client:
        result = client.post(
            "/graphql", json={"query": query, "variables": {"from": iso(ACTIVITY_FROM), "to": iso(END)}}
        ).json()
    assert "errors" not in result, result["errors"]


def _accepts_depth(base, depth):
    try:
        Settings.from_env({**base, "MAX_QUERY_DEPTH": str(depth)})
    except ValueError:
        return False
    return True


@pytest.fixture(scope="module")
def split_node(pg):
    # Row A: the official score, points only 20 days ago. Row B: no score,
    # points in the last day. Every field must describe the same row (A).
    with psycopg.connect(pg.get_connection_url(), autocommit=True) as conn:
        ids = [
            conn.execute(
                "INSERT INTO nodes (block_producer_key, updated_at, score, score_percent, application_status)"
                " VALUES (%s, now(), %s, %s, false) RETURNING id",
                (SPLIT, score, score_percent),
            ).fetchone()[0]
            for score, score_percent in [(2000, 92.5), (None, None)]
        ]
        old = range(20 * DAY_BATCHES, 21 * DAY_BATCHES)
        for node_id, ks in zip(ids, [old, range(DAY_BATCHES)], strict=True):
            conn.execute(
                "INSERT INTO points (node_id, bot_log_id)"
                " SELECT %s, id FROM bot_logs WHERE batch_end_epoch = ANY(%s)",
                (node_id, [END - k * BATCH for k in ks]),
            )
        yield
        conn.execute("DELETE FROM points WHERE node_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM points_summary WHERE node_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM nodes WHERE id = ANY(%s)", (ids,))


def test_duplicate_nodes_rows_resolve_to_one_row(gql, split_node):
    query = """
    query ($key: String!, $from: DateTime!, $to: DateTime!) {
      blockProducer(publicKey: $key) {
        officialScore { score }
        day: uptime(window: DAY) { points }
        month: uptime(window: MONTH) { points }
        activity(from: $from, to: $to, bucket: DAY) { totals { points } }
      }
    }
    """
    result = gql(query, key=SPLIT, **{"from": iso(ACTIVITY_FROM), "to": iso(END)})
    assert "errors" not in result, result["errors"]
    bp = result["data"]["blockProducer"]
    assert bp["officialScore"]["score"] == 2000
    assert bp["day"]["points"] == 0
    assert bp["month"]["points"] == DAY_BATCHES
    assert bp["activity"]["totals"]["points"] == 0
